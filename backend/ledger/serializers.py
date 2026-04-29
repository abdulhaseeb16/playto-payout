from rest_framework import serializers

from .models import BankAccount, Merchant, Payout


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            'id',
            'account_number',
            'ifsc_code',
            'account_holder_name',
            'is_primary',
        ]


class MerchantSerializer(serializers.ModelSerializer):
    bank_accounts = BankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email', 'created_at', 'bank_accounts']


class PayoutSerializer(serializers.ModelSerializer):
    bank_account_last4 = serializers.SerializerMethodField()

    class Meta:
        model = Payout
        fields = [
            'id',
            'merchant',
            'bank_account',
            'amount_paise',
            'status',
            'attempt_count',
            'idempotency_key',
            'failure_reason',
            'created_at',
            'updated_at',
            'processing_started_at',
            'bank_account_last4',
        ]

    def get_bank_account_last4(self, obj):
        return obj.bank_account.account_number[-4:]


class MerchantDashboardSerializer(serializers.ModelSerializer):
    bank_accounts = BankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email', 'bank_accounts']
