# -*- coding: utf-8 -*-
{
    'name': "ADK Bloc-Note de Stock",
    'version': '18.0.2.1.0',
    'category': 'Inventory/Inventory',
    'summary': "Carnet de bord parallèle des entrées et sorties, sans aucun impact sur le stock réel : "
               "historique complet à régulariser plus tard dans Inventaire, Achats et Facturation.",
    'author': "Kambeu Henang Ange Duval",
    'maintainer': "Kambeu Henang Ange Duval <duvalkambeu61@gmail.com>",
    'license': 'LGPL-3',
    'depends': ['stock', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/memo_config_data.xml',
        'views/stock_memo_views.xml',
        'report/stock_memo_report_template.xml',
    ],
    'images': ['static/description/banner.png', 'static/description/ecran_01_saisie_mouvements.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
