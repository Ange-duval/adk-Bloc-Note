# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ADKStockReportWizard(models.TransientModel):
    _name = 'adk.stock.report.wizard'
    _description = "Assistant Rapport Bloc-Note"

    date_start = fields.Date(string="Date début", required=True, default=fields.Date.context_today)
    date_end = fields.Date(string="Date fin", required=True, default=fields.Date.context_today)
    state_filter = fields.Selection(
        [('all', "Toutes les lignes"), ('pending', "À régulariser uniquement"), ('done', "Régularisées uniquement")],
        string="Statut", default='all', required=True)
    type_filter = fields.Selection(
        [('all', "Entrées et sorties"), ('in', "Entrées uniquement"), ('out', "Sorties uniquement")],
        string="Mouvements", default='all', required=True)

    def action_print_pdf(self):
        self.ensure_one()
        if self.date_end < self.date_start:
            raise UserError(_("La date de fin doit être postérieure ou égale à la date de début."))
        data = {
            'date_start': fields.Date.to_string(self.date_start),
            'date_end': fields.Date.to_string(self.date_end),
            'state_filter': self.state_filter,
            'type_filter': self.type_filter,
        }
        return self.env.ref('adk_stock_line_no_impact.action_report_adk_memo').report_action(self, data=data)
