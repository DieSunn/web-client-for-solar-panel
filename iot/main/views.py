from datetime import datetime
import time
from django.views.generic import View
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from .models import Solar_Panel, Characteristics, Hub, Panel, PanelData, LatestPanelData, PanelStatus, PanelType
from django.views.decorators.csrf import csrf_exempt
from django.core import serializers
from django.db import connections, ProgrammingError, OperationalError, transaction
from django.utils.dateparse import parse_date, parse_time # Для парсинга строк даты/времени
import requests
import json
from django.template.defaultfilters import date
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils.decorators import method_decorator
import os
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import SolarPanelSerializer, CharacteristicsSerializer
from datetime import timedelta
from django.utils import timezone
import logging # Recommended for logging errors
from .services import sync_all_panel_data, SyncResult
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from .forms import HubForm
import uuid
from django.db import connections, transaction


logger = logging.getLogger(__name__)


#Тут заменить на api сервера
EXTERNAL_API_URL = "http://85.193.80.133:8080"  


class DashboardView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        # Получаем все панели
        panels = Panel.objects.select_related('hub') \
                              .all() \
                              .order_by('id_panel')

        # Ночной режим из cookie или GET-параметра
        night_mode = request.COOKIES.get('night_mode', 'off')
        if 'night_mode' in request.GET:
            night_mode = request.GET['night_mode']

        # AJAX‑запрос за данными панели
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            selected = request.GET.get('selected_panel')
            if selected == 'all':
                records = PanelData.objects.all().order_by('-date', 'time')
            else:
                records = PanelData.objects.filter(
                    id_panel=selected
                ).order_by('-date', 'time')

            data = serializers.serialize('json', records)
            return JsonResponse({'data': data})

        # Рендер обычного GET
        context = {
            'panels': panels,
            'night_mode': night_mode,
        }
        response = render(request, 'dashboard.html', context)
        response.set_cookie('night_mode', night_mode)
        return response

class SolarPanelsView(View):
    def get(self, request, *args, **kwargs):
        panels = Panel.objects.select_related('hub').all().order_by('id_panel')

        panel_list = []
        for panel in panels:
            panel_list.append({
                'id_panel': panel.id_panel,
                'hub_id': panel.hub.id_hub if panel.hub else None,
                'coordinates': panel.coordinates if hasattr(panel, 'coordinates') else None,
            })
            
        return JsonResponse(panel_list, safe=False)
    
# Получение данных по конкретной солнечной установке
def get_characteristics_data_by_panel(request, panel_id):
    # фильтруем по переданному panel id.
    characteristics = Characteristics.objects.filter(solar_panel_id=panel_id)

    # Подготовка данных для графика
    generated_power = [c.generated_power for c in characteristics]
    consumed_power = [c.consumed_power for c in characteristics]
    date = [c.date for c in reversed(characteristics)]

    # Сериализация данных в JSON
    data = {
        'generated_power': generated_power,
        'consumed_power': consumed_power,
        'date': date,
    }
    return JsonResponse(data)

# забор характеристик по заданному дню
def get_characteristics_by_date(request, panel_id, selected_date):
    try:
        date_object = datetime.strptime(selected_date, '%Y-%m-%d')
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # Выбираем все записи Characteristics за переданный id и дату
    characteristics = Characteristics.objects.filter(
        solar_panel_id=panel_id, date=date_object)

    generated_power = [c.generated_power for c in characteristics]
    consumed_power = [c.consumed_power for c in characteristics]
    date = [c.date for c in characteristics]
    time =[c.time for c in characteristics]
    data = {
        'generated_power': generated_power,
        'consumed_power': consumed_power,
        'date': date,
        'time': time,
    }
    return JsonResponse(data)

def get_general_characteristics_data(request):
    """
    Возвращает данные для графиков:
    - фильтрация по panel_id (строка) или все панели при 'all' или отсутствии параметра
    - фильтрация по range: 'day', 'week', 'month'
    - или фильтрация по start/end (YYYY-MM-DD)
    """
    qs = PanelData.objects.all()

    # 1) Фильтрация по панели
    panel_id = request.GET.get('panel_id')
    if panel_id and panel_id != 'all':
        qs = qs.filter(id_panel=panel_id)

    # 2) Фильтрация по диапазону
    date_range = request.GET.get('range')
    today = timezone.localdate()
    if date_range == 'day':
        qs = qs.filter(date=today)
    elif date_range == 'week':
        qs = qs.filter(date__gte=today - timedelta(days=6), date__lte=today)
    elif date_range == 'month':
        qs = qs.filter(date__gte=today - timedelta(days=29), date__lte=today)
    else:
        # если переданы start и end — используем их
        start = request.GET.get('start')
        end   = request.GET.get('end')
        if start and end:
            qs = qs.filter(date__range=[start, end])

    # 3) Сортировка по времени
    qs = qs.order_by('date', 'time')

    # 4) Формируем массивы для JS
    generated_power = list(qs.values_list('generated_power', flat=True))
    consumed_power  = list(qs.values_list('consumed_power', flat=True))
    # Для дат склеиваем date+time в ISO‑строку
    date = [
        f"{rec.date.isoformat()}T{rec.time.isoformat()}"
        for rec in qs.only('date', 'time')
    ]

    data = {
        'generated_power': generated_power,
        'consumed_power': consumed_power,
        'date': date,
    }
    return JsonResponse(data)

# # Класс представления table.html
# class CharTableView(View):
#     def get(self, request, *args, **kwargs):
#         night_mode = request.COOKIES.get('night_mode', 'off')

#         # Проверяем параметр 'night_mode' в GET запросе
#         if 'night_mode' in request.GET:
#             night_mode = request.GET['night_mode']

#         char = Characteristics.objects.order_by('-date', '-time')
#         solar_panels = Solar_Panel.objects.all().order_by('id')

#         # Инициализация пагинатора на 10 элементов/страница
#         paginator = Paginator(char, 10)
#         page_number=request.GET.get('page')

#         try:
#             characteristics=paginator.page(page_number)
#         except PageNotAnInteger:
#             # Если номер страницы не является целым числом, отображаем первую страницу
#             characteristics = paginator.page(1)
#         except EmptyPage:
#              # Если страница находится за пределами доступных страниц, отображаем последнюю страницу
#             characteristics = paginator.page(paginator.num_pages)

#         response = render(request, "table.html", {
#                           'characteristics': characteristics, 
#                           'night_mode': night_mode, 
#                           "solar_panels": solar_panels,
#                           })
#         response.set_cookie('night_mode', night_mode)

#         return response

class CharTableView(View):
    def get(self, request, *args, **kwargs):
        night_mode = request.COOKIES.get('night_mode', 'off')
        if 'night_mode' in request.GET:
            night_mode = request.GET['night_mode']

        panel_data_records = PanelData.objects.order_by('-date', '-time')
        solar_panels = Solar_Panel.objects.all().order_by('id')


        panels = Panel.objects.select_related('hub').all().order_by('id_panel')
        hubs = Hub.objects.all().order_by('id_hub')


        paginator = Paginator(panel_data_records, 10)
        page_number = request.GET.get('page')

        try:
            page_obj = paginator.page(page_number) 
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        response = render(request, "table.html", {

                            'panel_data_records': page_obj,
                            'night_mode': night_mode,
                            "solar_panels": solar_panels,
                            "panels": panels, 
                            "hubs": hubs, 
                            })

        # Set the night mode cookie
        response.set_cookie('night_mode', night_mode)

        return response


# panels.html
def solar_panels(request):
    night_mode = request.COOKIES.get('night_mode', 'off')
    connected_clients = get_connected_clients(request)
    # Декодирование содержимого JsonResponse и преобразование в Python-словарь
    connected_clients_content = connected_clients.content.decode(
        'utf-8')  # Получить содержимое как строку
    # Преобразовать строку JSON в словарь
    connected_clients_data = json.loads(connected_clients_content)

    # Извлечение ключей из словаря
    connected_clients = list(connected_clients_data.keys())
    print(connected_clients)
    solar = Solar_Panel.objects.all().order_by('id')
    return render(request, "panels.html", {'panels': solar, 'night_mode': night_mode, 'connected_clients': connected_clients})

# ??? TODO DOC (ALEXEY)
def characteristics_data(request):
    selected_panel_id = request.GET.get('solar_panel')
    if selected_panel_id:
        characteristics = Characteristics.objects.filter(
            solar_panel_id=selected_panel_id)
    else:
        characteristics = Characteristics.objects.all()

    data = {
        'dates': [char.date.strftime("%Y-%m-%d") for char in characteristics],
        'generated_power': [char.generated_power for char in characteristics],
        'consumed_power': [char.consumed_power for char in characteristics],
    }

    return JsonResponse(data)

# устарело: представление socket.html
def socket(request):
    night_mode = request.COOKIES.get('night_mode', 'off')

    sol = Solar_Panel.objects.all()
    return render(request, "socket.html", {'night_mode': night_mode})


# Самая последняя запись характеристик панели (JSON)
def get_recent_char(request, panel_id):
    try:
        characteristics = Characteristics.objects.filter(
            solar_panel_id=panel_id).latest('date', 'time')
        # Формируем данные для JSON-ответа
        data = {
            'horizontal_position': f"{characteristics.horizontal_position}°",
            'vertical_position': f"{characteristics.vertical_position}°",
            'consumed_power': f"{characteristics.consumed_power:.2f}",
            'generated_power': f"{characteristics.generated_power:.2f} w",
            'date': date(characteristics.date, "DATE_FORMAT"),
            'time': characteristics.time.strftime("%H:%M"),
        }

        return JsonResponse(data)
    except Characteristics.DoesNotExist:
        return JsonResponse({'error': 'Characteristics not found'}, status=404)

def panel_detail(request):
    night_mode = request.COOKIES.get('night_mode', 'off')
    # Извлечение ID панели из GET-запроса
    panel_id = request.GET.get('id')
    characteristics = Characteristics.objects.filter(
        solar_panel_id=panel_id).latest('date', 'time')

    # Получение объекта панели из базы данных или возврат 404, если такой панель не найдена
    panel = get_object_or_404(Solar_Panel, id=panel_id)

    context = {
        'panel': panel,
        'night_mode': night_mode,
        'char': characteristics,
    }

    return render(request, "panel_detail.html", context)

# получение погоды (OpenWeatherAPI)
def get_weather(request, city="Chita"):
    try:
        api_key = 'f8e3947fda7d5cb9ce646407ff31d731'  # ключ для доступа
        base_url = 'http://api.openweathermap.org/data/2.5/weather'  # базовая ссылка к api

        # доп. параметры добавляемые к базовой ссылке
        params = {
            'q': city,  # город по умолчанию Чита
            'appid': api_key,  # ключ доступа
            'units': 'metric',  # Для получения погоды в метрической системе
            'lang': 'ru',  # Добавляем параметр lang для получения данных на русском
        }

        response = requests.get(base_url, params=params)  # запрос к api погоды
        response.raise_for_status()  # Генерирует исключение, если ответ содержит ошибку

        weather_data = response.json()  # парсим погоду с запроса к api
        # получаем направление ветра, преобразуем его из градусного в обычный вид
        wind = wind_direction(weather_data['wind']['deg'])
        # на интерфейс передаем обычный вид направления ветра
        weather_data['wind']['deg'] = wind
        return JsonResponse(weather_data)
    except requests.exceptions.RequestException as e:
        # Обработка исключений, связанных с запросом к API OpenWeatherMap
        print(f"Ошибка при запросе к OpenWeatherMap: {e}")
        return JsonResponse({'error': f"Ошибка при запросе к OpenWeatherMap: {e}"}, status=500)
    except KeyError as e:
        # Обработка исключений, связанных с отсутствием ожидаемых ключей в ответе API
        print(f"Ошибка при обработке ответа OpenWeatherMap: {e}")
        return JsonResponse({'error': f"Ошибка при обработке ответа OpenWeatherMap: {e}"}, status=500)
    except Exception as e:
        # Обработка других неожиданных исключений
        print(f"Необработанная ошибка: {e}")
        return JsonResponse({'error': f"Необработанная ошибка: {e}"}, status=500)


# направление ветра согласно полученным градусам с openweatherapi
def wind_direction(degrees):
    if degrees >= 337.5 or degrees < 22.5:
        return 'Северный'
    elif 22.5 <= degrees < 67.5:
        return 'Северо-восточный'
    elif 67.5 <= degrees < 112.5:
        return 'Восточный'
    elif 112.5 <= degrees < 157.5:
        return 'Юго-восточный'
    elif 157.5 <= degrees < 202.5:
        return 'Южный'
    elif 202.5 <= degrees < 247.5:
        return 'Юго-западный'
    elif 247.5 <= degrees < 292.5:
        return 'Западный'
    elif 292.5 <= degrees < 337.5:
        return 'Северо-западный'
    else:
        return 'Неизвестное направление'

def test_chart(request):
    characteristic = Characteristics.objects.all()

    points = pd.read_csv("../iot/main/coordinates.csv")

    fig = px.line(
        x = [c.date for c in characteristic],
        y = [c.consumed_power for c in characteristic],
    ) 

    fig1 = px.scatter_mapbox(
        points, 
        lat="lat", 
        lon="lon", 
        hover_name="Name",
        color_continuous_scale=px.colors.cyclical.IceFire, 
        size_max=15, 
        zoom=10,        
        mapbox_style="carto-positron")

    chart = fig.to_html()
    chart1= fig1.to_html()

    context = {'chart': chart, 'chart1': chart1}
    return render (request, 'test_chart.html', context)


# Представление для данных характеристик солнечной панели
def solar_panel_characteristics(request, panel_id):
    characteristics = Characteristics.objects.filter(solar_panel_id=panel_id).order_by('-date', 'time')[:10]  # Берем последние 10 записей
    data = {
        'labels': [str(c.date) + ' ' + str(c.time) for c in characteristics],
        'datasets': [{
            'label': 'Generated Power',
            'data': [c.generated_power for c in characteristics],
        }, {
            'label': 'Consumed Power',
            'data': [c.consumed_power for c in characteristics],
        }]
    }
    return JsonResponse(data)

class SolarPanelViewSet(viewsets.ModelViewSet):
    queryset = Solar_Panel.objects.all().order_by('id')
    serializer_class = SolarPanelSerializer

class CharacteristicsViewSet(viewsets.ModelViewSet):
    queryset = Characteristics.objects.all()  # Добавлено для определения basename
    serializer_class = CharacteristicsSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['solar_panel']
    
    def get_queryset(self):
        queryset = super().get_queryset().order_by('-date', 'time')
        solar_panel_id = self.request.query_params.get('solar_panel', None)
        if solar_panel_id:
            queryset = queryset.filter(solar_panel_id=solar_panel_id)
        start_date = self.request.query_params.get('start', None)
        end_date = self.request.query_params.get('end', None)
        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        return queryset


# Пример API для погоды через OpenWeatherAPI
class WeatherAPIView(APIView):
    def get(self, request, format=None):
        city = request.query_params.get('city', 'Chita')
        api_key = 'f8e3947fda7d5cb9ce646407ff31d731'  # Рекомендуется вынести в settings или переменные окружения
        base_url = 'http://api.openweathermap.org/data/2.5/weather'
        params = {
            'q': city,
            'appid': api_key,
            'units': 'metric',
            'lang': 'ru',
        }
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            weather_data = response.json()
            wind_deg = weather_data.get('wind', {}).get('deg', None)
            if wind_deg is not None:
                weather_data['wind']['deg'] = wind_direction(wind_deg)
            return Response(weather_data)
        except requests.exceptions.RequestException as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def wind_direction(degrees):
    if degrees >= 337.5 or degrees < 22.5:
        return 'Северный'
    elif 22.5 <= degrees < 67.5:
        return 'Северо-восточный'
    elif 67.5 <= degrees < 112.5:
        return 'Восточный'
    elif 112.5 <= degrees < 157.5:
        return 'Юго-восточный'
    elif 157.5 <= degrees < 202.5:
        return 'Южный'
    elif 202.5 <= degrees < 247.5:
        return 'Юго-западный'
    elif 247.5 <= degrees < 292.5:
        return 'Западный'
    elif 292.5 <= degrees < 337.5:
        return 'Северо-западный'
    else:
        return 'Неизвестное направление'
    
class DataSubmissionAPIView(APIView):
    """
    API endpoint для внесения данных о характеристиках панели.
    Поддерживает:
      - POST: Принимает JSON-данные, валидирует их с помощью CharacteristicsSerializer и сохраняет в БД.
      - GET: Возвращает список записей с опциональной фильтрацией по solar_panel и диапазону дат.
    """

    def post(self, request, format=None):
        serializer = CharacteristicsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        queryset = Characteristics.objects.all().order_by('-date', 'time')
        solar_panel_id = request.query_params.get('solar_panel')
        start_date = request.query_params.get('start')
        end_date = request.query_params.get('end')
        if solar_panel_id:
            queryset = queryset.filter(solar_panel_id=solar_panel_id)
        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        serializer = CharacteristicsSerializer(queryset, many=True)
        return Response(serializer.data)
    
class ManagementView(View):
    def get(self, request, *args, **kwargs):
        night_mode = request.COOKIES.get('night_mode', 'off')
        if 'night_mode' in request.GET:
            night_mode = request.GET['night_mode']

        hubs = Hub.objects.prefetch_related('panel_set').order_by('id_hub')

        context = {
            'hubs': hubs,
            'night_mode': night_mode,
        }
        return render(request, 'management.html', context)

class PanelDetailView(View):
    def get(self, request, hub_id, panel_id, *args, **kwargs):
        night_mode = request.COOKIES.get('night_mode', 'off')
        if 'night_mode' in request.GET:
            night_mode = request.GET['night_mode']

        panel = get_object_or_404(Panel.objects.select_related('hub'), hub__id_hub=hub_id, id_panel=panel_id)

        context = {
            'panel': panel,
            'night_mode': night_mode,
        }
        return render(request, 'panel_detail.html', context)


# @method_decorator(csrf_exempt, name='dispatch')
# class ApiCommandView(View):
#     def post(self, request, *args, **kwargs):
#         try:
#             data = json.loads(request.body)
#             command = data.get("command")
#             hub_id = data.get("hubId")
#             panel_id = data.get("panelId")
#             vertical_position = data.get("verticalPosition")
#             horizontal_position = data.get("horizontalPosition")

#             headers = {
#                 "Content-Type": "application/json",
#                 "Authorization": "key1-admin",
#             }

#             # проверка обязательных полей
#             if not command or not hub_id:
#                 return JsonResponse({"status": "error", "message": "Command and HubId are required"}, status=400)

#             if command in ["SEND_DATA", "ROTATE",] and panel_id:
#                  api_payload["PanelId"] = panel_id

#             if command == "ROTATE":
#                 if vertical_position is not None and horizontal_position is not None:
#                     api_payload["VerticalPosition"] = vertical_position
#                     api_payload["HorizontalPosition"] = horizontal_position
#                 else:
#                     return JsonResponse({"status": "error", "message": "VerticalPosition and HorizontalPosition are required for ROTATE command"}, status=400)

#             # собираем нагрузку
#             api_payload = {"Command": command, "HubId": hub_id}
#             # ... добавляем PanelId, позиции и т.д.

#             # шлём запрос
#             response = requests.post(EXTERNAL_API_URL, json=api_payload, headers=headers)

#             if response.status_code != 200:
#                 pass

#             # если запрос успешен и это команда проверки статуса
#             if command in ["CHECK_STATUS", "STATUS"]:
#                 # разбираем body
#                 try:
#                     api_response_data = response.json()
#                 except json.JSONDecodeError:
#                     api_response_data = response.text

#                 # пытаемся синхронизировать до тех пор, пока есть новые данные или не вышли по таймауту
#                 max_retries = 5
#                 delay_seconds = 2
#                 for attempt in range(max_retries):
#                     sync_result: SyncResult = sync_all_panel_data()
#                     if sync_result.status == 'success':
#                         return JsonResponse({
#                             "status": "success",
#                             "api_response": api_response_data,
#                             "sync": {
#                                 "hubs_created": sync_result.hubs,
#                                 "panels_created": sync_result.panels,
#                                 "records_created": sync_result.records,
#                                 "message": sync_result.message
#                             }
#                         })
#                     elif sync_result.status == 'error':
#                         return JsonResponse({
#                             "status": "error",
#                             "message": "Error during sync",
#                             "details": sync_result.message
#                         }, status=500)
#                     # если 'no_data', ждём и повторяем
#                     time.sleep(delay_seconds)

#                 # таймаут: данные не пришли
#                 return JsonResponse({
#                     "status": "error",
#                     "message": f"Timeout waiting for database update after {max_retries * delay_seconds} seconds"
#                 }, status=504)

#             # для всех прочих команд просто возвращаем ответ API
#             if response.status_code == 200:
#                 try:
#                     return JsonResponse({"status": "success", "api_response": response.json()})
#                 except json.JSONDecodeError:
#                     return JsonResponse({"status": "success", "message": "Command sent, but non-JSON response", "api_response": response.text})
#         except Exception as e:
#             return JsonResponse({"status": "error", "message": str(e)}, status=500)
@method_decorator(csrf_exempt, name='dispatch')
class ApiCommandView(View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            command = data.get("command")
            hub_id = data.get("hubId")
            panel_id = data.get("panelId")
            vertical_position = data.get("verticalPosition")
            horizontal_position = data.get("horizontalPosition")

            headers = {
                "Content-Type": "application/json",
                "Authorization": "key1-admin",
            }

            if not command or not hub_id:
                return JsonResponse({"status": "error", "message": "Command and HubId are required"}, status=400)

            api_payload = {"Command": command, "HubId": hub_id}

            if command in ["SEND_DATA", "ROTATE", "STATUS", "CHECK_STATUS"] and panel_id:
                api_payload["PanelId"] = panel_id

            if command == "ROTATE":
                if vertical_position is not None and horizontal_position is not None:
                    api_payload["VerticalPosition"] = vertical_position
                    api_payload["HorizontalPosition"] = horizontal_position
                else:
                    return JsonResponse({"status": "error", "message": "VerticalPosition and HorizontalPosition are required for ROTATE command"}, status=400)

            response = requests.post(EXTERNAL_API_URL, json=api_payload, headers=headers)

            if response.status_code == 200:
                try:
                    api_response_data = response.json()
                    return JsonResponse({"status": "success", "api_response": api_response_data})
                except json.JSONDecodeError:
                    return JsonResponse({"status": "success", "message": "Command sent successfully, but API response is not JSON.", "api_response": response.text})
            else:
                try:
                    api_response_data = response.json()
                    return JsonResponse({"status": "error", "message": f"API returned status code {response.status_code}", "api_response": api_response_data}, status=response.status_code)
                except json.JSONDecodeError:
                    return JsonResponse({"status": "error", "message": f"API returned status code {response.status_code}", "api_response": response.text}, status=response.status_code)


        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON in request body"}, status=400)
        except requests.exceptions.RequestException as e:
            return JsonResponse({"status": "error", "message": f"Error communicating with external API: {e}"}, status=500)
        except Exception as e:
            return JsonResponse({"status": "error", "message": f"An unexpected error occurred: {e}"}, status=500)

def sync_latest_panel_data_to_main_models(request):
    db_alias = 'solar_panel_db'
    fetched_data = {}
    hubs_created = panels_created = records_created = 0

    # 1) Fetch latest data per (panel, hub)
    try:
        with connections[db_alias].cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT ON (id_panel, id_hub)
                    id_panel, id_hub, generated_power, consumed_power,
                    vertical_position, horizontal_position, date, time,
                    status, battery_charge
                FROM panel_data
                ORDER BY id_panel, id_hub, date DESC, time DESC;
            """)
            cols = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                fetched_data[(row[0], row[1])] = dict(zip(cols, row))

    except KeyError:
        msg = f"Alias '{db_alias}' not in DATABASES"
        logger.error(msg)
        return JsonResponse({'status': 'error', 'error': msg}, status=500)
    except (ProgrammingError, OperationalError) as e:
        logger.exception("Error reading from secondary DB")
        return JsonResponse({'status': 'error', 'error': 'Fetch error from secondary DB'}, status=500)
    except Exception:
        logger.exception("Unexpected error during fetch")
        return JsonResponse({'status': 'error', 'error': 'Unexpected fetch error'}, status=500)

    # 2) Sync into main DB
    try:
        with transaction.atomic():
            # Ensure Hubs and Panels exist for all fetched keys
            for (panel_id, hub_id) in fetched_data.keys():
                hub, created = Hub.objects.get_or_create(
                    id_hub=hub_id,
                    defaults={'ip_address': 'unknown', 'port': 0}
                )
                if created:
                    hubs_created += 1
                    logger.info(f"Created Hub {hub_id}")

                panel, created = Panel.objects.get_or_create(
                    id_panel=panel_id,
                    hub=hub,
                    defaults={'type': PanelType.STATIC, 'coordinates': None}
                )
                if created:
                    panels_created += 1
                    logger.info(f"Created Panel {panel_id} for Hub {hub_id}")

            # Insert only where actual data exists
            for (panel_id, hub_id), data in fetched_data.items():
                record_date = parse_date(str(data['date'])) if data['date'] else None
                record_time = parse_time(str(data['time'])) if data['time'] else None
                status_value = data.get('status')
                valid_status = status_value if status_value in PanelStatus.values else None
                if status_value and valid_status is None:
                    logger.warning(f"Invalid status '{status_value}' for {panel_id}@{hub_id}")

                defaults = {
                    'generated_power': data.get('generated_power'),
                    'consumed_power': data.get('consumed_power'),
                    'vertical_position': data.get('vertical_position'),
                    'horizontal_position': data.get('horizontal_position'),
                    'status': valid_status,
                    'battery_charge': data.get('battery_charge'),
                }

                panel_data, created = PanelData.objects.update_or_create(
                    id_panel=panel_id,
                    id_hub=hub_id,
                    date=record_date,
                    time=record_time,
                    defaults=defaults
                )
                if created:
                    records_created += 1

        msg = (
            f"Sync complete: hubs={hubs_created}, panels={panels_created}, "
            f"data records={records_created}."
        )
        logger.info(msg)
        return JsonResponse({'status': 'success', 'message': msg,
                            'hubs_created': hubs_created,
                            'panels_created': panels_created,
                            'panel_data_created': records_created},
                            status=200)

    except Exception:
        logger.exception("Unexpected error during save")
        return JsonResponse({'status': 'error', 'error': 'Unexpected save error'}, status=500)


@method_decorator(staff_member_required, name='dispatch')
class CreateHubView(View):
    """
    Представление для создания нового хаба.
    Обрабатывает GET-запросы для отображения формы и POST-запросы для сохранения данных.
    """
    template_name = 'create_hub.html'
    secondary_alias = 'solar_panel_db' # Псевдоним для вторичной базы данных

    def get(self, request):
        form = HubForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = HubForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        id_hub = form.cleaned_data['id_hub']
        ip = form.cleaned_data['ip_address']
        port = form.cleaned_data['port']
        count = form.cleaned_data['panel_count']
        prefix = form.cleaned_data['panel_prefix']
        ptype = form.cleaned_data['panel_type']

        # Запись во вторичную БД (прямые SQL запросы)
        try:
            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    # Вставка хаба
                    cursor.execute(
                        """
                        INSERT INTO hub (id_hub, ip_address, port)
                        VALUES (%s, %s, %s)
                        """, [id_hub, ip, port]
                    )
                    # Вставка панелей
                    for i in range(1, count + 1):
                        panel_id = f"{prefix}_{i}"
                        cursor.execute(
                            """
                            INSERT INTO id_panel (id_panel, type, id_hub)
                            VALUES (%s, %s, %s)
                            """, [panel_id, ptype, id_hub]
                        )
            logger.info(f"Hub '{id_hub}' and {count} panels successfully added to secondary DB.")
        except (ProgrammingError, OperationalError) as e:
            logger.exception(f"Secondary DB write failed for hub '{id_hub}': {e}")
            form.add_error(None, f"Ошибка при сохранении во вторичную БД: {e}")
            return render(request, self.template_name, {'form': form})
        except Exception as e:
            logger.exception(f"Unexpected error during secondary DB write for hub '{id_hub}': {e}")
            form.add_error(None, f"Неожиданная ошибка при сохранении во вторичную БД: {e}")
            return render(request, self.template_name, {'form': form})


        # Если запись во вторичную БД прошла успешно, зеркалируем в основную БД (Django ORM)
        try:
            with transaction.atomic():
                # Создание хаба в основной БД
                hub_obj, hub_created = Hub.objects.get_or_create(
                    id_hub=id_hub,
                    defaults={'ip_address': ip, 'port': port}
                )
                if hub_created:
                    logger.info(f"Created Hub in primary DB: {id_hub}")
                else:
                    # Если хаб уже существует в основной БД (но не во вторичной, т.к. там прошла уникальность)
                    # это может быть нежелательной ситуацией, но в данном случае get_or_create обновит defaults
                    logger.warning(f"Hub '{id_hub}' already exists in primary DB, updating if necessary.")
                    hub_obj.ip_address = ip
                    hub_obj.port = port
                    hub_obj.save()


                # Создание объектов Panel в основной БД
                for i in range(1, count + 1):
                    panel_id = f"{prefix}_{i}"
                    panel_obj, panel_created = Panel.objects.get_or_create(
                        id_panel=panel_id,
                        hub=hub_obj,
                        defaults={'type': ptype, 'coordinates': None} # Учитываем 'coordinates' из модели
                    )
                    if panel_created:
                        logger.info(f"Created Panel '{panel_id}' in primary DB for Hub '{id_hub}'")
                    else:
                        logger.warning(f"Panel '{panel_id}' already exists in primary DB for Hub '{id_hub}', updating if necessary.")
                        panel_obj.type = ptype
                        # panel_obj.coordinates = None # Можно обновить, если нужно
                        panel_obj.save()

            logger.info(f"Hub '{id_hub}' and associated panels successfully mirrored to primary DB.")
            return redirect('hub_list') # Перенаправляем на список хабов после успешного создания

        except Exception as e:
            logger.exception(f"Primary DB mirror failed for hub '{id_hub}': {e}")
            # Внимание: если сюда попали, вторичная БД уже содержит данные.
            # Возможно, потребуется логика для отката или ручного вмешательства.
            form.add_error(None, f"Ошибка при зеркалировании в основную БД: {e}")
            return render(request, self.template_name, {'form': form})


@method_decorator(staff_member_required, name='dispatch')
class HubListView(View):
    """
    Представление для отображения списка всех хабов.
    """
    template_name = 'hub_list.html'

    def get(self, request):
        hubs = Hub.objects.all().order_by('id_hub') # Получаем все хабы из основной БД
        return render(request, self.template_name, {'hubs': hubs})


@method_decorator(staff_member_required, name='dispatch')
class HubUpdateView(View):
    """
    Представление для редактирования существующего хаба.
    Использует id_hub в качестве первичного ключа для поиска.
    """
    template_name = 'hub_edit.html' # Мы создадим этот шаблон, он будет похож на create_hub.html
    secondary_alias = 'solar_panel_db'

    def get(self, request, pk):
        # Получаем объект хаба из основной БД по pk (id_hub)
        hub = get_object_or_404(Hub, pk=pk)
        # Инициализируем форму данными из объекта хаба
        # panel_count и panel_prefix не передаются, так как они не редактируются
        form = HubForm(initial={
            'id_hub': hub.id_hub,
            'ip_address': hub.ip_address,
            'port': hub.port,
            # Исправлено: используем hub.panel_set вместо hub.panels
            'panel_type': hub.panel_set.first().type if hub.panel_set.first() else None # Заполняем тип первой панели
        }, instance=hub) # Передаем instance для валидации id_hub

        return render(request, self.template_name, {'form': form, 'hub': hub})

    def post(self, request, pk):
        hub = get_object_or_404(Hub, pk=pk)
        form = HubForm(request.POST, instance=hub) # Передаем instance для валидации и обновления

        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'hub': hub})

        # Получаем данные, которые разрешено редактировать
        new_id_hub = form.cleaned_data['id_hub']
        new_ip = form.cleaned_data['ip_address']
        new_port = form.cleaned_data['port']
        new_panel_type = form.cleaned_data['panel_type']

        # --- Обновление во вторичной БД (прямые SQL запросы) ---
        try:
            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    # Обновление хаба во вторичной БД
                    cursor.execute(
                        """
                        UPDATE hub
                        SET ip_address = %s, port = %s, id_hub = %s
                        WHERE id_hub = %s
                        """, [new_ip, new_port, new_id_hub, hub.id_hub] # Старый id_hub для WHERE, новый для SET
                    )
                    # Если id_hub изменился, нужно также обновить id_hub в связанных панелях во вторичной БД
                    if new_id_hub != hub.id_hub:
                        cursor.execute(
                            """
                            UPDATE id_panel
                            SET id_hub = %s
                            WHERE id_hub = %s
                            """, [new_id_hub, hub.id_hub]
                        )
                    # Обновление типа всех панелей, связанных с этим хабом, во вторичной БД
                    # (предполагаем, что тип панели одинаков для всех панелей одного хаба)
                    cursor.execute(
                        """
                        UPDATE id_panel
                        SET type = %s
                        WHERE id_hub = %s
                        """, [new_panel_type, new_id_hub]
                    )

            logger.info(f"Hub '{hub.id_hub}' (now '{new_id_hub}') successfully updated in secondary DB.")
        except (ProgrammingError, OperationalError) as e:
            logger.exception(f"Secondary DB update failed for hub '{hub.id_hub}': {e}")
            form.add_error(None, f"Ошибка при обновлении во вторичной БД: {e}")
            return render(request, self.template_name, {'form': form, 'hub': hub})
        except Exception as e:
            logger.exception(f"Unexpected error during secondary DB update for hub '{hub.id_hub}': {e}")
            form.add_error(None, f"Неожиданная ошибка при обновлении во вторичную БД: {e}")
            return render(request, self.template_name, {'form': form, 'hub': hub})


        # --- Обновление в основной БД (Django ORM) ---
        try:
            with transaction.atomic():
                # Обновляем сам объект хаба в основной БД
                hub.id_hub = new_id_hub # Обновляем PK, если он изменился
                hub.ip_address = new_ip
                hub.port = new_port
                hub.save()
                logger.info(f"Hub '{hub.id_hub}' successfully updated in primary DB.")

                # Обновляем тип всех связанных панелей в основной БД
                # (предполагаем, что тип панели одинаков для всех панелей одного хаба)
                # Исправлено: используем hub.panel_set вместо hub.panels
                hub.panel_set.update(type=new_panel_type)
                logger.info(f"Panels for Hub '{hub.id_hub}' successfully updated in primary DB.")

            return redirect('hub_list') # Перенаправляем на список хабов после успешного обновления

        except Exception as e:
            logger.exception(f"Primary DB update mirror failed for hub '{hub.id_hub}': {e}")
            form.add_error(None, f"Ошибка при зеркалировании обновления в основную БД: {e}")
            return render(request, self.template_name, {'form': form, 'hub': hub})


@method_decorator(staff_member_required, name='dispatch')
class HubDeleteView(View):
    """
    Представление для удаления хаба.
    Отображает страницу подтверждения и выполняет удаление из обеих баз данных.
    """
    template_name = 'hub_confirm_delete.html' # Новый шаблон для подтверждения удаления
    secondary_alias = 'solar_panel_db'

    def get(self, request, pk):
        hub = get_object_or_404(Hub, pk=pk)
        return render(request, self.template_name, {'hub': hub})

    def post(self, request, pk):
        hub = get_object_or_404(Hub, pk=pk)

        # --- Удаление во вторичной БД (прямые SQL запросы) ---
        try:
            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    # Сначала удаляем связанные записи из panel_data
                    cursor.execute(
                        """
                        DELETE FROM panel_data
                        WHERE id_hub = %s AND id_panel IN (SELECT id_panel FROM id_panel WHERE id_hub = %s)
                        """, [hub.id_hub, hub.id_hub]
                    )
                    logger.info(f"Deleted PanelData for Hub '{hub.id_hub}' from secondary DB.")

                    # Затем удаляем связанные панели из id_panel
                    cursor.execute(
                        """
                        DELETE FROM id_panel
                        WHERE id_hub = %s
                        """, [hub.id_hub]
                    )
                    logger.info(f"Deleted Panels for Hub '{hub.id_hub}' from secondary DB.")

                    # И только потом удаляем сам хаб из hub
                    cursor.execute(
                        """
                        DELETE FROM hub
                        WHERE id_hub = %s
                        """, [hub.id_hub]
                    )
                    logger.info(f"Hub '{hub.id_hub}' successfully deleted from secondary DB.")
        except (ProgrammingError, OperationalError) as e:
            logger.exception(f"Secondary DB deletion failed for hub '{hub.id_hub}': {e}")
            # Возвращаем пользователя на страницу подтверждения с ошибкой
            return render(request, self.template_name, {'hub': hub, 'error': f"Ошибка при удалении из вторичной БД: {e}"})
        except Exception as e:
            logger.exception(f"Unexpected error during secondary DB deletion for hub '{hub.id_hub}': {e}")
            return render(request, self.template_name, {'hub': hub, 'error': f"Неожиданная ошибка при удалении из вторичной БД: {e}"})

        # --- Удаление в основной БД (Django ORM) ---
        try:
            with transaction.atomic():
                hub.delete() # Удаление хаба из основной БД (CASCADE удалит связанные панели)
            logger.info(f"Hub '{hub.id_hub}' successfully deleted from primary DB.")
            return redirect('hub_list') # Перенаправляем на список хабов после успешного удаления
        except Exception as e:
            logger.exception(f"Primary DB deletion mirror failed for hub '{hub.id_hub}': {e}")
            # Внимание: если сюда попали, вторичная БД уже удалила данные.
            # Возможно, потребуется логика для отката или ручного вмешательства.
            return render(request, self.template_name, {'hub': hub, 'error': f"Ошибка при зеркалировании удаления в основную БД: {e}"})

