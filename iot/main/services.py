import logging
from django.db import connections, transaction
from django.db.utils import ProgrammingError, OperationalError
from datetime import datetime
from .models import Hub, Panel, PanelData, PanelStatus, PanelType
from django.utils.dateparse import parse_date, parse_time

logger = logging.getLogger(__name__)

class SyncResult:
    def __init__(self, status, hubs=0, panels=0, records=0, message=''):
        self.status = status          # 'success', 'no_data' или 'error'
        self.hubs = hubs
        self.panels = panels
        self.records = records
        self.message = message

def sync_all_panel_data():
    """
    Синхронизирует всю историю panel_data из внешней БД.
    Будут загружены все записи, которых ещё нет в локальной БД,
    определяемых по (id_panel, id_hub, date, time).
    """
    db_alias = 'solar_panel_db'
    fetched = []
    try:
        with connections[db_alias].cursor() as cursor:
            # Убираем DISTINCT ON, получаем все строки
            cursor.execute("""
                SELECT
                    id_panel, id_hub, generated_power, consumed_power,
                    vertical_position, horizontal_position, date, time,
                    status, battery_charge
                FROM panel_data;
            """)
            cols = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                fetched.append(dict(zip(cols, row)))
    except KeyError as e:
        msg = f"DB alias {db_alias} not found: {e}"
        logger.error(msg)
        return SyncResult('error', message=msg)
    except (ProgrammingError, OperationalError) as e:
        msg = f"Error fetching from {db_alias}: {e}"
        logger.exception(msg)
        return SyncResult('error', message=msg)

    if not fetched:
        return SyncResult('no_data')

    hubs_created = panels_created = recs_created = 0
    try:
        with transaction.atomic():
            for item in fetched:
                hub, hc = Hub.objects.get_or_create(
                    id_hub=item['id_hub'],
                    defaults={'ip_address': 'unknown','port': 0}
                )
                hubs_created += int(hc)

                panel, pc = Panel.objects.get_or_create(
                    id_panel=item['id_panel'],
                    hub=hub,
                    defaults={'type': PanelType.STATIC, 'coordinates': None}
                )
                panels_created += int(pc)

                d = parse_date(str(item['date'])) if item['date'] else None
                t = parse_time(str(item['time'])) if item['time'] else None
                status = item['status'] if item['status'] in PanelStatus.values else None
                if item['status'] and status is None:
                    logger.warning(f"Invalid status {item['status']} for {item['id_panel']}@{item['id_hub']}")

                # Проверяем, есть ли уже такая запись
                exists = PanelData.objects.filter(
                    id_panel=item['id_panel'],
                    id_hub=item['id_hub'],
                    date=d,
                    time=t
                ).exists()
                if not exists:
                    PanelData.objects.create(
                        id_panel=item['id_panel'],
                        id_hub=item['id_hub'],
                        generated_power=item['generated_power'],
                        consumed_power=item['consumed_power'],
                        vertical_position=item['vertical_position'],
                        horizontal_position=item['horizontal_position'],
                        date=d, time=t, status=status,
                        battery_charge=item['battery_charge']
                    )
                    recs_created += 1

    except (ProgrammingError, OperationalError) as e:
        msg = f"DB error saving: {e}"
        logger.exception(msg)
        return SyncResult('error', message=msg)
    except Exception as e:
        msg = f"Unexpected error saving data: {e}"
        logger.exception(msg)
        return SyncResult('error', message=msg)

    return SyncResult(
        'success',
        hubs=hubs_created,
        panels=panels_created,
        records=recs_created,
        message=f"Created Hubs: {hubs_created}, Panels: {panels_created}, New PanelData: {recs_created}"
    )
