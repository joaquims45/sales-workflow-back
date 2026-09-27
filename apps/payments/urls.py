from django.urls import path

from . import views

urlpatterns = [
    path("<str:external_reference>/", views.mock_checkout_page, name="mock-checkout-page"),
    path("<str:external_reference>/approve/", views.approve_mock_payment, name="mock-checkout-approve"),
    path("<str:external_reference>/reject/", views.reject_mock_payment, name="mock-checkout-reject"),
]
