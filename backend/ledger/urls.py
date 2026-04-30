from django.urls import path

from .views import APIIndexView, MerchantDashboardView, PayoutCreateView, PayoutDetailView

urlpatterns = [
    path('', APIIndexView.as_view()),
    path('payouts/', PayoutCreateView.as_view()),
    path('merchants/<uuid:merchant_id>/dashboard/', MerchantDashboardView.as_view()),
    path('merchants/<uuid:merchant_id>/payouts/', PayoutCreateView.as_view()),
    path('merchants/<uuid:merchant_id>/payouts/<uuid:payout_id>/', PayoutDetailView.as_view()),
]
