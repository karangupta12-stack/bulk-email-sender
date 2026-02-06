# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_excel, name='upload_excel'),
    path('compose/', views.compose_email, name='compose_email'),
    path('export/<int:campaign_id>/', views.export_report, name='export_report'),
    
    # --- NEW URLs ---
    path('contacts/', views.manage_contacts, name='manage_contacts'),
    path('contacts/add/', views.add_contact, name='add_contact'),
    path('contacts/edit/<int:id>/', views.edit_contact, name='edit_contact'),
    path('contacts/delete/<int:id>/', views.delete_contact, name='delete_contact'),
    path('contacts/delete-all/', views.delete_all_contacts, name='delete_all_contacts'),
    
    path('campaign/delete/<int:campaign_id>/', views.delete_campaign, name='delete_campaign'),
    path('campaign/failed/<int:campaign_id>/', views.get_failed_emails, name='get_failed_emails'),
]