from django.urls import include, path
from . import views
# from .views import Reading
from .views import *
from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'solar-panels', SolarPanelViewSet)  # Для этого класса атрибут queryset есть
router.register(r'characteristics', CharacteristicsViewSet, basename='characteristics')


urlpatterns = [
    path('', DashboardView.as_view(), name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('get-characteristics-data/<int:panel_id>/', views.get_characteristics_data_by_panel,
         name='get-characteristics-data-by-panel'),  # сводка по конкретной панели
       path('get_characteristics_by_date/<int:panel_id>/<str:selected_date>/', views.get_characteristics_by_date, name='get_characteristics_by_date'),
  # сводка по конкретной панели и дате
    path('get-general-characteristics-data/', get_general_characteristics_data,
         name='get-general-characteristics-data'),  # сводка общая
    path('socket/', views.socket, name='socket'), # устарело
    path('table/', CharTableView.as_view(), name='table'),
    path('characteristics-data/', characteristics_data,
         name='characteristics-data'),
    path('get_recent_char/<int:panel_id>/', views.get_recent_char, name='get_recent_char'),
    path('test_chart/', views.test_chart, name='test_chart'),
    path('panel-characteristics/<int:panel_id>/', views.solar_panel_characteristics, name='panel_characteristics'),
    path('api/', include(router.urls)),
    path('api/data-submission/', DataSubmissionAPIView.as_view(), name='data-submission'),
    path('solar-panels/', SolarPanelsView.as_view(), name='solar-panels'),
    path('manage/', views.ManagementView.as_view(), name='manage_panels'),
    path('manage/<str:hub_id>/<str:panel_id>/', views.PanelDetailView.as_view(), name='panel_detail'),
    path('api/send_command/', views.ApiCommandView.as_view(), name='api_send_command'),
    path('api/sync-panel-data/', views.sync_latest_panel_data_to_main_models, name='sync_latest_panel_data'),
    path('admin-area/create-hub/', views.CreateHubView.as_view(), name='create_hub'),
]
