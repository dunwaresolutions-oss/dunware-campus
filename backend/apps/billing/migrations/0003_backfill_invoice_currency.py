from django.db import migrations


def fill(apps, schema_editor):
    Invoice = apps.get_model("billing", "Invoice")
    SiteConfiguration = apps.get_model("core", "SiteConfiguration")
    cfg = SiteConfiguration.objects.first()
    code = (cfg.currency if cfg else "CAD") or "CAD"
    Invoice.objects.filter(currency="").update(currency=code)


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0002_invoice_currency"),
        ("core", "0002_siteconfiguration"),
    ]

    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
