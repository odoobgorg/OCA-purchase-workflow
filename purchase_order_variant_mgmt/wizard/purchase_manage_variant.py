# -*- coding: utf-8 -*-
# Copyright 2016 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import openerp.addons.decimal_precision as dp
from openerp import api, fields, models


class PurchaseManageVariant(models.TransientModel):
    _name = 'purchase.manage.variant'

    product_tmpl_id = fields.Many2one(
        comodel_name='product.template', string="Template", required=True)
    # This is a many2many because Odoo fails to fill one2many in onchanges
    variant_line_ids = fields.Many2many(
        comodel_name='purchase.manage.variant.line', string="Variant Lines")

    # HACK: https://github.com/OCA/server-tools/pull/492#issuecomment-237594285
    @api.multi
    def onchange(self, values, field_name, field_onchange):  # pragma: no cover
        if "variant_line_ids" in field_onchange:
            for sub in ("product_id", "disabled", "value_x", "value_y",
                        "product_uom_qty"):
                field_onchange.setdefault("variant_line_ids." + sub, u"")
        return super(PurchaseManageVariant, self).onchange(
            values, field_name, field_onchange)

    @api.onchange('product_tmpl_id')
    def _onchange_product_tmpl_id(self):
        self.variant_line_ids = [(6, 0, [])]
        template = self.product_tmpl_id
        context = self.env.context
        record = self.env[context['active_model']].browse(
            context['active_id'])
        if context['active_model'] == 'purchase.order.line':
            purchase_order = record.order_id
        else:
            purchase_order = record
        if template and len(template.attribute_line_ids) >= 2:
            line_x = template.attribute_line_ids[0]
            line_y = template.attribute_line_ids[1]
            lines = []
            for value_x in line_x.value_ids:
                for value_y in line_y.value_ids:
                    # Filter the corresponding product for that values
                    product = template.product_variant_ids.filtered(
                        lambda x: (value_x in x.attribute_value_ids and
                                   value_y in x.attribute_value_ids))
                    order_line = purchase_order.order_line.filtered(
                        lambda x: x.product_id == product)
                    lines.append((0, 0, {
                        'product_id': product,
                        'disabled': not bool(product),
                        'value_x': value_x,
                        'value_y': value_y,
                        'product_uom_qty': order_line.product_qty,
                    }))
            self.variant_line_ids = lines

    @api.multi
    def button_transfer_to_order(self):
        context = self.env.context
        record = self.env[context['active_model']].browse(context['active_id'])
        if context['active_model'] == 'purchase.order.line':
            purchase_order = record.order_id
        else:
            purchase_order = record
        OrderLine = self.env['purchase.order.line']
        lines2unlink = OrderLine
        for line in self.variant_line_ids:
            order_line = purchase_order.order_line.filtered(
                lambda x: x.product_id == line.product_id)
            if order_line:
                if not line.product_uom_qty:
                    # Done this way because there's a side effect removing here
                    lines2unlink |= order_line
                else:
                    order_line.product_qty = line.product_uom_qty
            elif line.product_uom_qty:
                order_line = OrderLine.new({
                    'product_id': line.product_id.id,
                    'order_id': purchase_order.id,
                })
                order_line.onchange_product_id()
                # This should be done later for handling supplier quantities
                order_line.product_qty = line.product_uom_qty
                order_line._onchange_quantity()
                order_line_vals = order_line._convert_to_write(
                    order_line._cache)
                purchase_order.order_line.create(order_line_vals)
        lines2unlink.unlink()


class PurchaseManageVariantLine(models.TransientModel):
    _name = 'purchase.manage.variant.line'

    product_id = fields.Many2one(
        comodel_name='product.product', string="Variant", readonly=True)
    disabled = fields.Boolean()
    value_x = fields.Many2one(comodel_name='product.attribute.value')
    value_y = fields.Many2one(comodel_name='product.attribute.value')
    product_uom_qty = fields.Float(
        string="Quantity", digits_compute=dp.get_precision('Product UoS'))
