# -*- coding: utf-8 -*-

from . import controllers
from . import models

def __init__(self, pool, cr):
    super(models.MyOtherModule, self).__init__(pool, cr)
    self._cr.execute("SELECT create_ir_cron(%s, %s, %s, %s, %s)",
                     ('logilab_mqtt_process', 10, 'logilab', 'process_mqtt_messages', '{}'))