# 支付：拆出「支付形态」字段 + 退款申请（人工受理队列）
#
# 1）**拆字段**：此前 `create_order` 把平台返回的形态（qrcode / jump / html）写进了
#    `pay_type`，调用方真正选的支付方式（alipay / wxpay）没存下来 —— 后台订单列表因此
#    只显示得出 `ezfp jump`，看不出「用什么付的」。本次拆成：
#        pay_type  调用方选择的支付方式（alipay / wxpay …）
#        pay_form  平台返回的形态（qrcode 二维码 / jump 收银台地址 / html 网页表单）
#    存量订单按「pay_type 的值是形态」做一次搬迁，并尽量从回调留痕的原文里恢复支付方式
#    （易支付通知里带 `type=alipay` 这类字段）；恢复不出来就留空，界面显示为「—」。
#
# 2）**退款申请**：易支付当前未对本商户开通「自助退款」（调退款接口会被回
#    「管理员未开启商户后台自助退款」）。这类渠道的退款改为「先受理、人工处理」：
#    落一条 pay_refund_request 待办，管理员在平台后台退完再回本站标记。
#    渠道能力由 `PayProvider.refund_mode` 决定（auto / manual），因此这里把 ezfp
#    置为 manual；平台哪天开通了，到控制台「支付设置」把它改回 auto 即可，不用改代码。
#
# 回滚：本迁移不可逆（无法区分「原本就是 auto 的渠道」）。如需恢复，
# 到控制台把渠道退款方式改回「自助退款」，订单两个字段照现状保留即可。

import django.db.models.deletion
import uuid
from django.db import migrations, models

#: 旧数据里被误写进 pay_type 的「支付形态」取值
LEGACY_FORMS = ('qrcode', 'jump', 'html')


def set_ezfp_manual_refund(apps, schema_editor):
    """易支付当前未开通自助退款 → 先配成「人工受理」（幂等，开通后可在后台改回）"""
    PayProvider = apps.get_model('API', 'PayProvider')
    PayProvider.objects.filter(code='ezfp').update(refund_mode='manual')


def normalize_legacy_orders(apps, schema_editor):
    """把存量订单的 pay_type（实为形态）搬到 pay_form，并尽量恢复真实支付方式"""
    PayOrder = apps.get_model('API', 'PayOrder')
    PayNotifyLog = apps.get_model('API', 'PayNotifyLog')

    for order in PayOrder.objects.filter(pay_type__in=LEGACY_FORMS):
        form = order.pay_type
        real_type = ''
        log = (PayNotifyLog.objects.filter(out_trade_no=order.out_trade_no, verified=True)
               .order_by('-create_time').first())
        if log is not None:
            for part in (log.raw or '').split('&'):
                key, _, value = part.partition('=')
                if key == 'type' and value:
                    real_type = value
                    break
        order.pay_type = real_type
        order.pay_form = form
        order.save(update_fields=['pay_type', 'pay_form'])


class Migration(migrations.Migration):

    dependencies = [
        ('API', '0056_pay_free_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='payorder',
            name='pay_form',
            field=models.CharField(blank=True, default='', help_text='平台返回的形态：qrcode 二维码 / jump 收银台地址 / html 网页表单；前端按它决定渲染方式', max_length=20, verbose_name='支付形态'),
        ),
        migrations.AddField(
            model_name='payprovider',
            name='refund_mode',
            field=models.CharField(choices=[('auto', '自助退款（调平台接口）'), ('manual', '人工受理（平台未开通自助退款）')], default='auto', help_text='人工受理：退款不调平台接口，改为落「待退款申请」，由管理员在平台后台退款后回本站标记', max_length=10, verbose_name='退款方式'),
        ),
        migrations.AddField(
            model_name='paysetting',
            name='refund_notice_days',
            field=models.PositiveIntegerField(default=7, help_text='渠道不支持自助退款时，回复申请人「人工审核后 N 个工作日内退款」；只影响文案，不参与任何计算', verbose_name='人工退款告知天数（工作日）'),
        ),
        migrations.AlterField(
            model_name='payorder',
            name='method',
            field=models.CharField(blank=True, default='web', help_text='下单时传给平台的 method：web / jump / jsapi / app / scan / applet', max_length=20, verbose_name='发起方式'),
        ),
        migrations.AlterField(
            model_name='payorder',
            name='pay_info',
            field=models.TextField(blank=True, default='', help_text='平台返回的 pay_info：pay_form=qrcode 时是二维码内容，jump 时是收银台地址，供前端展示', verbose_name='支付参数'),
        ),
        migrations.AlterField(
            model_name='payorder',
            name='pay_type',
            field=models.CharField(blank=True, default='', help_text='调用方选择的支付方式：alipay / wxpay …', max_length=20, verbose_name='支付方式'),
        ),
        migrations.CreateModel(
            name='PayRefundRequest',
            fields=[
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='申请ID')),
                ('out_trade_no', models.CharField(db_index=True, max_length=64, verbose_name='商户订单号')),
                ('provider_code', models.CharField(blank=True, db_index=True, default='', max_length=32, verbose_name='支付渠道')),
                ('amount', models.DecimalField(decimal_places=2, help_text='不得大于「订单金额 − 已退金额 − 其它待处理申请金额」', max_digits=14, verbose_name='申请退款金额（元）')),
                ('status', models.CharField(choices=[('pending', '待人工处理'), ('refunded', '已退款'), ('rejected', '已驳回')], db_index=True, default='pending', max_length=20, verbose_name='状态')),
                ('source', models.CharField(choices=[('api', '接入项目发起'), ('user', '用户申请'), ('console', '管理员登记')], default='user', help_text='谁提的这条申请，便于人工核实时回访', max_length=10, verbose_name='申请来源')),
                ('contact', models.CharField(blank=True, default='', help_text='申请人留的联系方式（可选），供人工核实', max_length=128, verbose_name='联系方式')),
                ('remark', models.CharField(blank=True, default='', max_length=255, verbose_name='申请说明')),
                ('operator', models.CharField(blank=True, default='', max_length=64, verbose_name='处理人')),
                ('handled_at', models.DateTimeField(blank=True, null=True, verbose_name='处理时间')),
                ('handle_note', models.CharField(blank=True, default='', help_text='驳回原因，或人工退款时填平台退款单号', max_length=255, verbose_name='处理备注')),
                ('applicant_app', models.ForeignKey(blank=True, help_text='对外调用时签名认证出的接入项目；用户申请时为空', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pay_refund_requests', to='API.userapp', verbose_name='申请项目')),
                ('applicant_user', models.ForeignKey(blank=True, help_text='本站充值订单的申请用户；接入项目发起时为空', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pay_refund_requests', to='API.user', verbose_name='申请用户')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refund_requests', to='API.payorder', verbose_name='支付订单')),
            ],
            options={
                'verbose_name': '退款申请',
                'verbose_name_plural': '退款申请',
                'db_table': 'pay_refund_request',
                'ordering': ['-create_time'],
                'indexes': [models.Index(fields=['order', '-create_time'], name='idx_pay_refund_order_time'), models.Index(fields=['status', '-create_time'], name='idx_pay_refund_status_time')],
            },
        ),
        migrations.RunPython(normalize_legacy_orders, migrations.RunPython.noop),
        migrations.RunPython(set_ezfp_manual_refund, migrations.RunPython.noop),
    ]
