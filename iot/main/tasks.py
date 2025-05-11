# tasks.py
from celery import shared_task
from django.db import connections
from django.utils.dateparse import parse_date, parse_time
from .models import Hub, Panel, PanelData, PanelStatus
from .views import sync_logic  # вынесите логику из sync_latest_panel_data_to_main_models в отдельную функцию

@shared_task(bind=True, default_retry_delay=5, max_retries=12)
def poll_for_panel_data(self, hub_id, panel_id, last_timestamp):
    """
    Периодически опрашивает secondary DB, пока не появится запись новее last_timestamp.
    Затем вызывает sync_logic для обновления основных моделей.
    """
    db_alias = 'solar_panel_db'
    with connections[db_alias].cursor() as cursor:
        cursor.execute("""
            SELECT date, time 
            FROM panel_data 
            WHERE id_hub=%s AND id_panel=%s 
              AND (date || ' ' || time) > %s
            ORDER BY date DESC, time DESC
            LIMIT 1
        """, [hub_id, panel_id, last_timestamp])
        row = cursor.fetchone()

    if row:
        # данные появились — запускаем синхронизацию
        sync_logic()  
        return 'synced'
    else:
        # повторяем после паузы
        raise self.retry()  
