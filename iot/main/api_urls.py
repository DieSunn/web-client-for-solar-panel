from django.urls import path 
from .api_views import PanelListAPIView, PanelDetailAPIView

urlpatterns = [ path('panels/', 
                     PanelListAPIView.as_view(), 
                     name='api-panels'), 
                     path('panels/int:pk/', 
                          PanelDetailAPIView.as_view(), 
                          name='api-panel-detail'), ]