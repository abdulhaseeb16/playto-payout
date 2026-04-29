from django.urls import path

from .views import MerchantDashboardView, PayoutCreateView, PayoutDetailView

urlpatterns = [
    path('merchants/<uuid:merchant_id>/dashboard/', MerchantDashboardView.as_view()),
    path('merchants/<uuid:merchant_id>/payouts/', PayoutCreateView.as_view()),
    path('merchants/<uuid:merchant_id>/payouts/<uuid:payout_id>/', PayoutDetailView.as_view()),
]
