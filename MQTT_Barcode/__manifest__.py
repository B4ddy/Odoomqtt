# -*- coding: utf-8 -*-
{
    'name': "MQTT_Barcode",
    'summary': "MQTT Connection Manager",
    'description': """MQTT Connection Manager""",
    'author': "Florian Süß",
    'website': "https://github.com/B4ddy",
    'category': 'Tools',
    'version': '1.0',
    'depends': ['base'],
    'data': [
        'views/barcode_mqtt.xml',
        'views/updater.xml',
    ],
    'installable': True,
    'application': True
}
