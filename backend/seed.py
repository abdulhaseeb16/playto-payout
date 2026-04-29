from ledger.models import Merchant


Merchant.objects.get_or_create(name='Playto Demo Merchant')
