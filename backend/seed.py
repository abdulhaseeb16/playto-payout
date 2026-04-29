"""
Run with: python manage.py shell < seed.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from ledger.models import Merchant, BankAccount, LedgerEntry

# Wipe existing data (safe for dev — idempotent re-run)
LedgerEntry.objects.all().delete()
BankAccount.objects.all().delete()
Merchant.objects.all().delete()

# Create exactly these 3 merchants with these exact names/emails:
agency     = Merchant.objects.create(name="Velocity Creative Agency", email="ops@velocityagency.in")
freelancer = Merchant.objects.create(name="Priya Sharma — Freelance Dev", email="priya@psd.in")
saas       = Merchant.objects.create(name="InvoiceZen SaaS", email="finance@invoicezen.io")

# Create one BankAccount per merchant with these exact values:
BankAccount.objects.create(
    merchant=agency, account_number="001234567890",
    ifsc_code="HDFC0001234", account_holder_name="Velocity Creative Agency Pvt Ltd", is_primary=True
)
BankAccount.objects.create(
    merchant=freelancer, account_number="9876543210",
    ifsc_code="ICIC0009876", account_holder_name="Priya Sharma", is_primary=True
)
BankAccount.objects.create(
    merchant=saas, account_number="1122334455",
    ifsc_code="SBIN0011223", account_holder_name="InvoiceZen Technologies Pvt Ltd", is_primary=True
)

# Seed credit history (these exact amounts and descriptions):
credits = [
    (agency,     250000,  "Client payment — Acme Corp USA — Invoice #1001"),
    (agency,     180000,  "Client payment — TechVentures UK — Invoice #1002"),
    (agency,     320000,  "Client payment — NordicStartup — Invoice #1003"),
    (freelancer,  75000,  "Project payment — React Dashboard — Client: StartupX"),
    (freelancer,  50000,  "Project payment — API Integration — Client: GrowthCo"),
    (saas,      1200000,  "Stripe Mirror — Monthly subscription revenue — April 2026"),
    (saas,       890000,  "Stripe Mirror — Monthly subscription revenue — March 2026"),
]

for merchant, amount, desc in credits:
    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type=LedgerEntry.CREDIT,
        amount_paise=amount,
        description=desc,
    )

# Print summary using derived balance (this verifies get_balance() works):
print("✅ Seed complete.")
for m in Merchant.objects.all():
    print(f"  {m.name}: ₹{m.get_balance()/100:.2f} available")
