# -*- coding: utf-8 -*-
from datetime import datetime, time

import pytz

from odoo import api, fields, models


class ReportAdkMemo(models.AbstractModel):
    _name = 'report.adk_stock_line_no_impact.report_adk_memo_template'
    _description = "Rapport Journal du Bloc-Note"

    @staticmethod
    def _fmt(qty):
        return ('%.2f' % (qty or 0.0)).rstrip('0').rstrip('.') or '0'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        d_start = fields.Date.to_date(data.get('date_start')) or fields.Date.context_today(self)
        d_end = fields.Date.to_date(data.get('date_end')) or d_start
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = tz.localize(datetime.combine(d_start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(d_end, time.max)).astimezone(pytz.utc).replace(tzinfo=None)

        domain = [('date', '>=', start), ('date', '<=', end)]
        if data.get('state_filter') in ('pending', 'done'):
            domain.append(('state', '=', data['state_filter']))
        if data.get('type_filter') in ('in', 'out'):
            domain.append(('type', '=', data['type_filter']))
        moves = self.env['adk.stock.memo'].search(domain, order='date asc, id asc')

        summary = {}
        for m in moves:
            row = summary.setdefault(m.adk_product_id.id, {
                'name': m.adk_product_id.name, 'qty_in': 0.0, 'qty_out': 0.0, 'pending': 0.0})
            sign = 1 if m.type == 'in' else -1
            row['qty_in' if m.type == 'in' else 'qty_out'] += m.qty
            if m.state == 'pending':
                row['pending'] += sign * m.qty
        rows = sorted(summary.values(), key=lambda r: r['name'] or '')

        labels = {'all': "Toutes", 'pending': "À régulariser", 'done': "Régularisées"}
        return {
            'doc_ids': docids,
            'doc_model': 'adk.stock.report.wizard',
            'company': self.env.company,
            'date_start': d_start.strftime('%d/%m/%Y'),
            'date_end': d_end.strftime('%d/%m/%Y'),
            'state_label': labels.get(data.get('state_filter') or 'all'),
            'moves': moves,
            'summary': rows,
            'total_in': sum(r['qty_in'] for r in rows),
            'total_out': sum(r['qty_out'] for r in rows),
            'total_pending': sum(r['pending'] for r in rows),
            'fmt': self._fmt,
            'printed_by': self.env.user.name,
            'printed_on': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M'),
        }
