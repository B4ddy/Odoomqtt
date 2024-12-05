import logging
import threading
import paho.mqtt.client as mqtt
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from functools import partial
from odoo.sql_db import db_connect

_logger = logging.getLogger(__name__)


##tldr: odoo create methode überschrieben so das mqtt client mit record gestartet wird,
## create ruft manual_subscribe auf, manual_subscribe stoppt client falls er schon läuft und startet ihn neu

class BarcodeMQTTModel(models.Model):
    _name = 'barcode_mqtt.model'
    _description = 'Model for BarcodeMQTT'

    name= fields.Char(string="Name", required=True)
    broker_host = fields.Char(string="Broker Host", required=True)
    broker_port = fields.Integer(string="Broker Port", required=True, default=1883)
    mqtt_topic = fields.Char(string="MQTT Topic", required=True)
    connection_status = fields.Char(string="Connection Status", default="Disconnected", readonly=True)
    last_message = fields.Text(string="Last Message", readonly=True)
    last_message_timestamp = fields.Integer(string="Last Message Timestamp", readonly=True)

    _mqtt_clients = {}
    _mqtt_lock = threading.Lock()

    #wenn ein record erstellt wird, wird der mqtt client gestartet
    @api.model
    def create(self, vals):
        # debug log
        _logger.info(f"Creating record with values: {vals}")

        record = super(BarcodeMQTTModel, self).create(vals)

        record.manual_subscribe()

        return record

    @api.model
    def _on_message(self, client, userdata, msg, record_id):
        try:
            payload = msg.payload.decode()
            _logger.info(f"Received message: '{payload}' on topic '{msg.topic}' for record {record_id}")

            with db_connect(self.env.registry.db_name).cursor() as cr:  # new cursor weil threadsafe
                env = api.Environment(cr, self.env.uid, self.env.context)
                record = env['barcode_mqtt.model'].browse(record_id).sudo()

                if record.exists():
                    record.with_context(from_mqtt=True).write({
                        'last_message': payload,
                        'last_message_timestamp': int(fields.Datetime.now().timestamp()),
                    })
                    cr.commit()

        except Exception as e:
            _logger.exception(f"Error processing message: {e}")

    def _on_connect(self, client, userdata, flags, rc, record):
        try:
            if rc == 0:
                with db_connect(self.env.registry.db_name).cursor() as cr:  # New Cursor
                    env = api.Environment(cr, self.env.uid, self.env.context)
                    record_in_new_env = env['barcode_mqtt.model'].browse(record.id).sudo()

                    _logger.info(
                        f"Connected to MQTT broker for record {record_in_new_env.id}. Subscribing to {record_in_new_env.mqtt_topic}")  # Accessing record in new env
                    client.subscribe(record_in_new_env.mqtt_topic)  # Accessing record in new env
                    record_in_new_env.with_context(from_mqtt=True).write({'connection_status': "Connected"})
                    cr.commit()


            else:
                with db_connect(self.env.registry.db_name).cursor() as cr:  # New Cursor
                    env = api.Environment(cr, self.env.uid, self.env.context)
                    record_in_new_env = env['barcode_mqtt.model'].browse(record.id).sudo()
                    error_message = f"Connection failed for {record_in_new_env.id} with code {rc}"
                    record_in_new_env.sudo().with_context(from_mqtt=True).write({'connection_status': error_message})
                    _logger.error(error_message)
                    cr.commit()  # fuck it


        except Exception as e:
            _logger.exception(f"Error in _on_connect for record {record.id}: {e}")


    def _on_disconnect(self, client, userdata, rc, record):
        try:
            if rc != 0:
                _logger.warning(f"Unexpected disconnect from MQTT broker for record {record.id}, code: {rc}.")
            record.sudo().with_context(from_mqtt=True).write({'connection_status': "Disconnected"})
        except Exception as e:
            _logger.exception(f"Error in _on_disconnect for record {record.id}: {e}")


## gibt es schon einen client für den record und ist er schon connected?
## wenn ja, dann wird nichts gemacht
## wenn nein, dann wird ein neuer client erstellt und connected

    def _start_mqtt_client(self):
        self.ensure_one()
        with self._mqtt_lock:
            if self.id in self._mqtt_clients and self._mqtt_clients[self.id].is_connected():
                _logger.debug(f"MQTT client already connected for record {self.id}")
                return

            try:
                client_id = f"odoo_mqtt_{self.id}"
                client = mqtt.Client(client_id=client_id, clean_session=False)  #clean_session=false behält subscriptions bei disconnect

                # callbacks
                ##partial wrappt die funktionen, damit sie die record id als parameter bekommen
                client.on_connect = partial(self._on_connect, record=self)
                client.on_disconnect = partial(self._on_disconnect, record=self)
                client.on_message = partial(self._on_message, record_id=self.id)

                _logger.debug(
                    f"Attempting to connect to MQTT broker {self.broker_host}:{self.broker_port} for record {self.id}")

                # connect to broker
                try:
                    client.connect(self.broker_host, self.broker_port, keepalive=60)
                    _logger.debug(f"Connected successfully to {self.broker_host}:{self.broker_port}")
                except Exception as e:
                    error_message = f"Failed to connect to broker {self.broker_host}:{self.broker_port} for record {self.id}: {e}"
                    _logger.exception(error_message)
                    self.sudo().write({'connection_status': f"Connection error: {e}"})
                    raise UserError(error_message)

                client.loop_start()  # start loop in background
                self._mqtt_clients[self.id] = client

                _logger.info(f"MQTT client loop started for record {self.id} with client ID {client_id}")

            except Exception as e:
                _logger.exception(f"An error occurred while starting MQTT client for record {self.id}: {e}")
                self.sudo().write({'connection_status': f"Setup error: {e}"})
                raise UserError(f"Error during MQTT client setup for record {self.id}: {e}")


    def _stop_mqtt_client(self):
        self.ensure_one()
        with self._mqtt_lock:
            client = self._mqtt_clients.get(self.id)
            if client:
                if client.is_connected():
                    client.loop_stop()
                    client.disconnect()
                    del self._mqtt_clients[self.id]
                    self.sudo().with_context(from_mqtt=True).write({'connection_status': "Disconnected"})
                    _logger.info(f"MQTT client stopped for {self.id}")
                else:
                    _logger.info(f"Client isn't currently running. Stopping client complete for {self.id} regardless.")

    def manual_subscribe(self):
        _logger.debug(f"Manual subscribe called for record {self.id}")
        self.ensure_one()         # self ist genau ein record
        self._stop_mqtt_client()  # stoppt client falls er schon läuft
        self._start_mqtt_client() # startet client neu
        _logger.debug(f"Manual subscribe completed for record {self.id}")

    def write(self, vals):
        _logger.debug(f"WRITE METHOD ENTERED with vals: {vals}")  # debug weil arsch
        res = super().write(vals)
        if not self.env.context.get('from_mqtt', False):
            relevant_fields = ['broker_host', 'broker_port', 'mqtt_topic']
            if any(field in vals for field in relevant_fields):
                for rec in self:
                    rec.manual_subscribe()
        return res

    @api.model
    def start_all_mqtt_clients(self):
        """Start MQTT clients for all records."""
        records = self.search([])
        for record in records:
            try:
                record.manual_subscribe()  # wird auch in create aufgerufen
                _logger.info(f"MQTT client started for record {record.id}.")
            except Exception as e:
                _logger.exception(f"Failed to start MQTT client for record {record.id}: {e}")

