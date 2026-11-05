# -*- coding: utf-8 -*-
"""ADK Bloc-Note de stock.

PRINCIPE : tout ce qui est saisi ici est un carnet de bord parallèle.
Aucune écriture n'est faite dans stock.move, stock.quant, stock.picking
ni dans la comptabilité : le stock réel d'Odoo n'est JAMAIS modifié.
Le magasinier note les entrées / sorties au moment où elles se produisent
sur le terrain, puis les marque « Régularisé » quand les documents officiels
(achat, réception, livraison, facture) ont été validés dans Odoo.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Champs « métier » figés quand une ligne est verrouillée
LOCKED_FIELDS = {'date', 'adk_product_id', 'type', 'qty', 'origin_ref',
                 'description', 'move_type_id', 'memo_partner_id'}


class ADKProductMemo(models.Model):
    _name = 'adk.product.memo'
    _description = 'Article du Bloc-Note'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string="Désignation", required=True)
    active = fields.Boolean(default=True)

    # Copie d'information seulement : aucun lien d'écriture vers l'article
    product_id = fields.Many2one(
        'product.product', string="Article Odoo d'origine",
        readonly=True, copy=False)
    uom_name = fields.Char(string="Unité", compute='_compute_uom_name')

    move_ids = fields.One2many('adk.stock.memo', 'adk_product_id', string="Mouvements")
    move_count = fields.Integer(string="Nb. mouvements", compute='_compute_move_count')

    qty_in = fields.Float(string="Total Entrées", compute='_compute_memo_stock', store=True)
    qty_out = fields.Float(string="Total Sorties", compute='_compute_memo_stock', store=True)
    qty_available = fields.Float(string="Stock Bloc-Note", compute='_compute_memo_stock', store=True)
    qty_pending = fields.Float(
        string="Solde à régulariser", compute='_compute_memo_stock', store=True,
        help="Entrées moins sorties des lignes pas encore régularisées dans Odoo.")
    pending_count = fields.Integer(
        string="Lignes à régulariser", compute='_compute_memo_stock', store=True)

    real_qty = fields.Float(
        string="Stock réel Odoo (info)", compute='_compute_real_qty',
        help="Lecture seule, à titre indicatif. Le Bloc-Note ne modifie jamais ce stock.")

    @api.depends('product_id')
    def _compute_uom_name(self):
        for rec in self:
            rec.uom_name = rec.product_id.uom_id.name or ''

    @api.depends('product_id')
    def _compute_real_qty(self):
        for rec in self:
            rec.real_qty = rec.product_id.qty_available if rec.product_id else 0.0

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    @api.depends('move_ids.qty', 'move_ids.type', 'move_ids.state')
    def _compute_memo_stock(self):
        for rec in self:
            total_in = sum(m.qty for m in rec.move_ids if m.type == 'in')
            total_out = sum(m.qty for m in rec.move_ids if m.type == 'out')
            pending = rec.move_ids.filtered(lambda m: m.state == 'pending')
            rec.qty_in = total_in
            rec.qty_out = total_out
            rec.qty_available = total_in - total_out
            rec.qty_pending = (sum(m.qty for m in pending if m.type == 'in')
                               - sum(m.qty for m in pending if m.type == 'out'))
            rec.pending_count = len(pending)

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Mouvements - %s", self.name),
            'res_model': 'adk.stock.memo',
            'view_mode': 'list,form',
            'domain': [('adk_product_id', '=', self.id)],
            'context': {'default_adk_product_id': self.id},
        }

    def unlink(self):
        for rec in self:
            if rec.move_ids:
                raise UserError(_(
                    "Suppression impossible : l'article « %s » possède des mouvements "
                    "enregistrés. Archivez-le plutôt.", rec.name))
        return super().unlink()

    # Synchronisation : copie des NOUVEAUX articles Odoo, rien d'autre.
    def action_sync_articles(self):
        existing = set(self.with_context(active_test=False).search([]).mapped('product_id').ids)
        products = self.env['product.product'].search([
            ('active', '=', True), ('type', '=', 'consu')])
        vals = [{'name': p.display_name, 'product_id': p.id}
                for p in products if p.id not in existing]
        if vals:
            self.create(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Synchronisation terminée"),
                'message': _("%s nouveaux articles copiés dans le Bloc-Note. "
                             "Le stock réel n'a pas été touché.", len(vals)),
                'sticky': False,
                'type': 'success',
            },
        }


class ADKStockMemo(models.Model):
    _name = 'adk.stock.memo'
    _description = 'Mouvement du Bloc-Note'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(string="N°", readonly=True, copy=False, default='/')

    adk_product_id = fields.Many2one(
        'adk.product.memo', string="Article Bloc-Note",
        required=True, ondelete='restrict', index=True, tracking=True)
    date = fields.Datetime(string="Date", default=fields.Datetime.now, required=True, tracking=True)
    type = fields.Selection(
        [('in', "ENTRÉE"), ('out', "SORTIE")],
        string="Sens", required=True, default='in', tracking=True)
    move_type_id = fields.Many2one(
        'adk.memo.type', string="Type de mouvement", ondelete='restrict', tracking=True,
        domain="[('direction', '=', type)]",
        help="Défini dans Configuration › Types de mouvement.")
    qty = fields.Float(string="Quantité", required=True, default=1.0, tracking=True)

    memo_partner_id = fields.Many2one(
        'adk.partner.memo', string="Tiers", ondelete='restrict', tracking=True,
        help="Client, fournisseur ou service. Choisissez dans la liste ou créez-le à la volée.")
    origin_ref = fields.Char(string="Document d'origine",
                             help="N° de bon de livraison, bon de commande, demande, facture…")
    description = fields.Text(string="Description")

    user_id = fields.Many2one('res.users', string="Magasinier",
                              default=lambda self: self.env.user, readonly=True)

    # Statut configurable ; "state" en reprend la signification (à régulariser / régularisé)
    status_id = fields.Many2one(
        'adk.memo.status', string="Statut", required=True, ondelete='restrict',
        default=lambda self: self._default_status_id(), tracking=True, index=True, copy=False)
    state = fields.Selection(related='status_id.kind', string="Situation", store=True, index=True)
    regul_ref = fields.Char(string="Document Odoo de régularisation", copy=False,
                            help="N° du transfert, de la réception, de la facture ou de l'ajustement "
                                 "d'inventaire qui a régularisé cette ligne.")
    regul_date = fields.Datetime(string="Régularisé le", readonly=True, copy=False)
    regul_user_id = fields.Many2one('res.users', string="Régularisé par", readonly=True, copy=False)

    is_locked = fields.Boolean(string="Verrouillé", default=False)

    @api.model
    def _default_status_id(self, kind='pending'):
        return self.env['adk.memo.status'].search(
            [('kind', '=', kind), ('active', '=', True)], order='sequence, id', limit=1).id

    # -- Cohérence sens / type de mouvement ---------------------------------
    @api.onchange('move_type_id')
    def _onchange_move_type_id(self):
        if self.move_type_id:
            self.type = self.move_type_id.direction

    @api.onchange('type')
    def _onchange_type(self):
        if self.move_type_id and self.move_type_id.direction != self.type:
            self.move_type_id = False

    @api.constrains('type', 'move_type_id')
    def _check_type_direction(self):
        for rec in self:
            if rec.move_type_id and rec.move_type_id.direction != rec.type:
                raise UserError(_("Le type « %(t)s » est une %(d)s : il ne correspond pas au sens choisi.",
                                  t=rec.move_type_id.name,
                                  d=dict(rec.move_type_id._fields['direction'].selection)[rec.move_type_id.direction].lower()))

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        MoveType = self.env['adk.memo.type']
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = seq.next_by_code('adk.stock.memo') or '/'
            if vals.get('move_type_id') and 'type' not in vals:
                vals['type'] = MoveType.browse(vals['move_type_id']).direction
        records = super().create(vals_list)
        # Une ligne créée directement avec un statut "régularisé" est verrouillée
        done = records.filtered(lambda r: r.state == 'done' and not r.regul_date)
        if done:
            done.write({'is_locked': True, 'regul_date': fields.Datetime.now(),
                        'regul_user_id': self.env.user.id})
        return records

    def write(self, vals):
        if LOCKED_FIELDS & set(vals) and any(rec.is_locked for rec in self):
            raise UserError(_("Cette ligne est verrouillée. Cliquez sur « Débloquer » pour la modifier."))
        if 'status_id' in vals:
            new = self.env['adk.memo.status'].browse(vals['status_id'])
            was_done = self.filtered(lambda r: r.state == 'done')
            was_pending = self - was_done
            is_manager = self.env.user.has_group('stock.group_stock_manager')
            if new.kind == 'pending' and was_done and not is_manager:
                raise UserError(_("Seul un responsable de stock peut remettre une ligne régularisée "
                                  "à un statut « À régulariser »."))
            res = super().write(vals)
            if new.kind == 'done' and was_pending:
                was_pending.write({'is_locked': True, 'regul_date': fields.Datetime.now(),
                                   'regul_user_id': self.env.user.id})
            elif new.kind == 'pending' and was_done:
                was_done.write({'is_locked': False, 'regul_date': False, 'regul_user_id': False})
            return res
        return super().write(vals)

    def unlink(self):
        if any(rec.is_locked or rec.state == 'done' for rec in self):
            raise UserError(_("Suppression impossible : une ligne verrouillée ou déjà régularisée "
                              "fait partie de l'historique."))
        return super().unlink()

    @api.constrains('qty')
    def _check_qty(self):
        for rec in self:
            if rec.qty <= 0:
                raise UserError(_("La quantité doit être supérieure à zéro."))

    # -- Verrouillage ------------------------------------------------------
    def action_lock(self):
        self.write({'is_locked': True})

    def action_unlock(self):
        if any(rec.state == 'done' for rec in self) and not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Seul un responsable de stock peut débloquer une ligne déjà régularisée."))
        self.write({'is_locked': False})

    # -- Régularisation ----------------------------------------------------
    def action_regularize(self):
        todo = self.filtered(lambda r: r.state == 'pending')
        if not todo:
            return
        status_id = self._default_status_id('done')
        if not status_id:
            raise UserError(_("Aucun statut « Régularisé » n'est configuré (Configuration › Statuts)."))
        todo.write({'status_id': status_id})

    def action_reset_pending(self):
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(_("Seul un responsable de stock peut remettre une ligne « À régulariser »."))
        status_id = self._default_status_id('pending')
        if not status_id:
            raise UserError(_("Aucun statut « À régulariser » n'est configuré (Configuration › Statuts)."))
        self.filtered(lambda r: r.state == 'done').write({'status_id': status_id})
