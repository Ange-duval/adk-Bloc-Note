# -*- coding: utf-8 -*-
"""Données de configuration du Bloc-Note : types de mouvement, statuts, tiers.

Comme pour les articles, les tiers sont une COPIE de travail : le module ne
modifie jamais les contacts, clients ou fournisseurs d'Odoo.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ADKMemoType(models.Model):
    _name = 'adk.memo.type'
    _description = "Type de mouvement du Bloc-Note"
    _order = 'sequence, id'

    name = fields.Char(string="Type de mouvement", required=True)
    direction = fields.Selection(
        [('in', "Entrée"), ('out', "Sortie")], string="Sens", required=True, default='in',
        help="Une entrée augmente le solde du Bloc-Note, une sortie le diminue.")
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(default=True)
    description = fields.Char(string="Description")
    move_ids = fields.One2many('adk.stock.memo', 'move_type_id', string="Mouvements")
    move_count = fields.Integer(string="Nb. mouvements", compute='_compute_move_count')

    _sql_constraints = [
        ('name_direction_uniq', 'unique(name, direction)',
         "Ce type de mouvement existe déjà pour ce sens."),
    ]

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    def write(self, vals):
        if 'direction' in vals and any(rec.move_ids and rec.direction != vals['direction'] for rec in self):
            raise UserError(_("Impossible de changer le sens d'un type déjà utilisé : "
                              "créez un nouveau type et archivez celui-ci."))
        return super().write(vals)

    def unlink(self):
        if any(rec.move_ids for rec in self):
            raise UserError(_("Ce type de mouvement est déjà utilisé : archivez-le au lieu de le supprimer."))
        return super().unlink()


class ADKMemoStatus(models.Model):
    _name = 'adk.memo.status'
    _description = "Statut du Bloc-Note"
    _order = 'sequence, id'

    name = fields.Char(string="Statut", required=True)
    kind = fields.Selection(
        [('pending', "Compte comme « À régulariser »"), ('done', "Compte comme « Régularisé »")],
        string="Ce statut signifie", required=True, default='pending',
        help="Un statut « Régularisé » verrouille la ligne et la retire du solde à régulariser. "
             "Vous pouvez créer autant de statuts intermédiaires que nécessaire "
             "(par exemple « En attente de facture »).")
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(default=True)
    move_ids = fields.One2many('adk.stock.memo', 'status_id', string="Mouvements")
    move_count = fields.Integer(string="Nb. mouvements", compute='_compute_move_count')

    _sql_constraints = [('name_uniq', 'unique(name)', "Ce statut existe déjà.")]

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    @api.model
    def _check_core_statuses(self):
        domain = [('active', '=', True)]
        if not self.search_count(domain + [('kind', '=', 'pending')]) or \
                not self.search_count(domain + [('kind', '=', 'done')]):
            raise UserError(_("Il faut conserver au moins un statut « À régulariser » "
                              "et un statut « Régularisé » actifs."))

    def write(self, vals):
        if 'kind' in vals and any(rec.move_ids and rec.kind != vals['kind'] for rec in self):
            raise UserError(_("Impossible de changer la signification d'un statut déjà utilisé : "
                              "créez un nouveau statut."))
        res = super().write(vals)
        if 'kind' in vals or 'active' in vals:
            self._check_core_statuses()
        return res

    def unlink(self):
        if any(rec.move_ids for rec in self):
            raise UserError(_("Ce statut est déjà utilisé : archivez-le au lieu de le supprimer."))
        res = super().unlink()
        self._check_core_statuses()
        return res


class ADKPartnerMemo(models.Model):
    _name = 'adk.partner.memo'
    _description = "Tiers du Bloc-Note (clients et fournisseurs)"
    _order = 'name'

    name = fields.Char(string="Nom du tiers", required=True)
    active = fields.Boolean(default=True)
    partner_type = fields.Selection(
        [('supplier', "Fournisseur"), ('customer', "Client"), ('both', "Client et fournisseur"),
         ('other', "Autre / service interne")],
        string="Nature", required=True, default='other')
    phone = fields.Char(string="Téléphone")
    note = fields.Char(string="Remarque")
    partner_id = fields.Many2one('res.partner', string="Contact Odoo d'origine",
                                 readonly=True, copy=False)
    move_ids = fields.One2many('adk.stock.memo', 'memo_partner_id', string="Mouvements")
    move_count = fields.Integer(string="Nb. mouvements", compute='_compute_counts')
    pending_count = fields.Integer(string="Lignes à régulariser", compute='_compute_counts')

    @api.depends('move_ids', 'move_ids.state')
    def _compute_counts(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)
            rec.pending_count = len(rec.move_ids.filtered(lambda m: m.state == 'pending'))

    @api.model
    def _guess_type(self, partner):
        customer = (getattr(partner, 'customer_rank', 0) or 0) > 0
        supplier = (getattr(partner, 'supplier_rank', 0) or 0) > 0
        if customer and supplier:
            return 'both'
        if customer:
            return 'customer'
        if supplier:
            return 'supplier'
        return 'other'

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Mouvements - %s", self.name),
            'res_model': 'adk.stock.memo',
            'view_mode': 'list,form',
            'domain': [('memo_partner_id', '=', self.id)],
            'context': {'default_memo_partner_id': self.id},
        }

    def unlink(self):
        if any(rec.move_ids for rec in self):
            raise UserError(_("Ce tiers possède des mouvements : archivez-le au lieu de le supprimer."))
        return super().unlink()

    # Copie des NOUVEAUX contacts Odoo. Aucun contact n'est modifié.
    def action_sync_partners(self):
        existing = set(self.with_context(active_test=False).search([]).mapped('partner_id').ids)
        partners = self.env['res.partner'].search([('active', '=', True), ('parent_id', '=', False)])
        vals = [{
            'name': p.display_name or p.name,
            'partner_id': p.id,
            'partner_type': self._guess_type(p),
            'phone': p.phone or False,
        } for p in partners if p.id not in existing and (p.display_name or p.name)]
        if vals:
            self.create(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Synchronisation terminée"),
                'message': _("%s nouveaux tiers copiés dans le Bloc-Note. "
                             "Vos contacts Odoo n'ont pas été modifiés.", len(vals)),
                'sticky': False,
                'type': 'success',
            },
        }
