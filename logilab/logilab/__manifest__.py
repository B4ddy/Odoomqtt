
{
    'name': "logilab",
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Live updates for Manufacturing Orders',
    'depends': ['base','mrp', 'web','mail'],
    'assets': {
        'web.assets_backend': [
            'logilab/static/src/js/mrp_production_form.js',
        ],
    },

'data': [
        # 'security/ir.model.access.csv',
        'views/manufacturing_order_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
