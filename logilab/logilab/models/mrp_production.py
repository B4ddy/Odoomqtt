from odoo import models, fields, api, _
import logging
import requests
import json
import re
from odoo import http
from odoo.addons.web.controllers.home import Home

#anderer ansatz kann eigentlich entfernt werden
class CustomHome(Home):
    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        res = super(CustomHome, self).web_login(redirect=redirect, **kw)
        if 'X-Frame-Options' in res.headers:
            res.headers.pop('X-Frame-Options')
        return res


_logger = logging.getLogger(__name__)
WEBSOCKET_URL = 'http://localhost:8080'  # Websocket URL -> ABgleichen mit odoo config file!!
WEBSOCKET_SECRET = 'logi'  # Websocket key -> ABgleichen mit odoo config file!!!


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    kistenreferenz_id = fields.Char('Kistenreferenz', size=13, required=False)
    show_produce = fields.Boolean(compute='_compute_show_buttons')
    show_produce_all = fields.Boolean(compute='_compute_show_buttons')
    is_planned = fields.Boolean(compute='_compute_is_planned')
    product_blueprint_url = fields.Char(compute='_compute_blueprint_url', string='Blueprint URL')


    # Geturl von attachment mit richtiger id

    @api.depends('product_id')
    def _compute_blueprint_url(self):
        for record in self:
            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', 'product.product'),
                ('res_id', '=', record.product_id.id),
                ('mimetype', '=', 'application/pdf')
            ], limit=1)

            if attachment:
                record.product_blueprint_url = f'/web/content/{attachment.id}?download=false'
            else:
                record.product_blueprint_url = False

    @api.depends('state', 'workorder_ids')
    def _compute_is_planned(self):
        for record in self:
            record.is_planned = any(wo.date_planned_start for wo in record.workorder_ids)

    @api.depends('move_raw_ids', 'state')
    def _compute_show_buttons(self):
        for record in self:
            is_ready = record.state in ('confirmed', 'progress') and record.move_raw_ids
            record.show_produce = is_ready
            record.show_produce_all = is_ready

    def get_blueprint_data(self):
        """Method to get blueprint data for frontend"""
        self.ensure_one()
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'product.product'),
            ('res_id', '=', self.product_id.id),
            ('mimetype', '=', 'application/pdf')
        ], limit=1)

        if attachment:
            return {
                'url': f'/web/content/{attachment.id}?download=false',
                'name': attachment.name
            }
        return False

    def _notify_websocket(self):
        #websocket payload für Abgleich in mrp_production_form.js
        try:
            self.ensure_one()
            data = {
                'id': self.id,
                'name': self.name,
                'state': self.state,
                'kistenreferenz': self.kistenreferenz_id,
                'show_produce': self.show_produce,
                'show_produce_all': self.show_produce_all,
                'is_planned': self.is_planned,
                'workorder_count': len(self.workorder_ids),
                'blueprint_url': self.product_blueprint_url,
                'timestamp': fields.Datetime.now().isoformat()
            }

            response = requests.post(
                f"{WEBSOCKET_URL}/update",
                json={'secret': WEBSOCKET_SECRET, 'data': data},
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            response.raise_for_status()
            _logger.info(f"WebSocket notification sent for MO {self.name} - Status: {self.state}")
        except Exception as e:
            _logger.exception(f"Error sending WebSocket notification for MO {self.name}: {e}")

    def write(self, vals):
        """write überschreiben für frontend notification"""
        res = super().write(vals)
        if any(field in vals for field in ('state', 'kistenreferenz_id', 'is_planned', 'workorder_ids')):
            self._notify_websocket()
        return res

    def _on_mqtt_last_message_changed(self, last_message):
        """Handle MQTT messages and trigger WebSocket updates"""
        try:
            try:
                parsed_message = json.loads(last_message)
                message = parsed_message.get('message', last_message)
            except (json.JSONDecodeError, TypeError):
                message = last_message

            mo_match = re.search(r'(WH/MO/\d{5})', message)
            if mo_match:
                mo_reference = mo_match.group(1)
                manufacturing_order = self.env['mrp.production'].search(
                    [('name', '=', mo_reference)], limit=1)
                if manufacturing_order:
                    _logger.info(f"Processing MO: {mo_reference}, Current State: {manufacturing_order.state}")
                    if "u0001" in message.lower() and manufacturing_order.state in ['progress', 'planned', 'confirmed']:
                        manufacturing_order.button_mark_done()
                        _logger.info(f"MO {mo_reference} marked as done")
                    elif manufacturing_order.state in ['confirmed', 'planned']:
                        manufacturing_order.action_start()
                        _logger.info(f"MO {mo_reference} started")
            else:
                _logger.info(f"No MO reference found in message: {message}")
        except Exception as e:
            _logger.exception(f"Error processing MQTT message: {e}")


   # Helpherfunctions um Websocket bei bestimmten Aktionen zu pingen.
    # Weitere funktionen von manufacturing order können überschrieben werden um Websocket zu pingen

    def action_confirm(self):
        res = super().action_confirm()
        self._notify_websocket()
        return res

    def action_start(self):
        res = super().action_start()
        self._notify_websocket()
        return res

    def button_mark_done(self):
        res = super().button_mark_done()
        self._notify_websocket()
        return res

    def button_plan(self):
        res = super().button_plan()
        self._notify_websocket()
        return res

    def button_unplan(self):
        res = super().button_unplan()
        self._notify_websocket()
        return res