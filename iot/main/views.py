from datetime import datetime
import time
from django.views.generic import View
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from .models import Solar_Panel, Characteristics, Hub, Panel, PanelData, LatestPanelData, PanelStatus, PanelType
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
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
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group
from .forms import *
import uuid
from django.db import connections, transaction
from .decorators import *


logger = logging.getLogger(__name__)


#Тут заменить на api сервера
EXTERNAL_API_URL = "http://85.193.80.133:8080"  
EXTERNAL_API_URLt = "http://192.168.1.157:5080"  
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hub_archives')

class DashboardView(View):
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

@method_decorator(login_required, name='dispatch')    
class SolarPanelViewSet(viewsets.ModelViewSet):
    queryset = Solar_Panel.objects.all().order_by('id')
    serializer_class = SolarPanelSerializer

@method_decorator(login_required, name='dispatch')    
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
@method_decorator(login_required, name='dispatch')    
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

@method_decorator(login_required, name='dispatch')    
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

@method_decorator(login_required, name='dispatch')     
class PanelDetailView(View):
    def get(self, request, hub_id, panel_id, *args, **kwargs):
        night_mode = request.COOKIES.get('night_mode', 'off')
        if 'night_mode' in request.GET:
            night_mode = request.GET['night_mode']

        panel = get_object_or_404(Panel.objects.select_related('hub'), hub__id_hub=hub_id, id_panel=panel_id)

        # Получаем последнюю запись PanelData для данной панели
        # Сортируем по дате и времени в убывающем порядке, затем берем первую (самую свежую)
        latest_panel_data = PanelData.objects.filter(
            id_hub=hub_id, 
            id_panel=panel_id,
        ).order_by('-date', '-time').first()


        context = {
            'panel': panel,
            'night_mode': night_mode,
            'latest_panel_data': latest_panel_data, # Передаем либо реальную, либо фиктивную запись PanelData
        }
        return render(request, 'panel_detail.html', context)

def guest_login_view(request):
    """
    Логинит пользователя как "Гость".
    Предполагается, что существует пользователь с именем 'guest_user'
    и он добавлен в группу 'Guest'.
    """
    if request.user.is_authenticated:
        # Если пользователь уже вошел, просто перенаправляем его
        return redirect('hub_list') # Или куда-либо еще

    try:
        # Находим пользователя 'guest_user'
        # Предполагаем, что такой пользователь существует
        guest_user = User.objects.get(username='guest_user')

        # Проверяем, что 'guest_user' принадлежит группе 'Guest'
        guest_group = Group.objects.get(name='Guest')
        if not guest_user.groups.filter(name='Guest').exists():
            guest_user.groups.add(guest_group)
            logger.info(f"Added user '{guest_user.username}' to 'Guest' group.")

        login(request, guest_user)
        logger.info(f"User '{guest_user.username}' logged in as guest.")
        return redirect('dashboard') # Перенаправляем на страницу, доступную гостю

    except User.DoesNotExist:
        logger.error("Attempted guest login, but 'guest_user' does not exist.")
        # Если пользователь 'guest_user' не найден, вы можете:
        # 1. Создать его программно (но это лучше делать через миграции или management command)
        # 2. Вывести сообщение об ошибке
        # 3. Перенаправить на страницу логина с ошибкой
        return redirect('login') # Или render('login_form.html', {'error': 'Guest user not configured.'})
    except Group.DoesNotExist:
        logger.error("Attempted guest login, but 'Guest' group does not exist.")
        return redirect('login')
    except Exception as e:
        logger.exception(f"Error during guest login: {e}")
        return redirect('login') # Fallback

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
@method_decorator(login_required, name='dispatch')    
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
            state = data.get('State')

            headers = {
                "Content-Type": "application/json",
                "Authorization": "key1-admin",
            }

            if not command or not hub_id:
                return JsonResponse({"status": "error", "message": "Command and HubId are required"}, status=400)

            api_payload = {"Command": command, "HubId": hub_id}

            if command in ["SEND_DATA", "ROTATE", "STATUS", "CHECK_STATUS", "AUTO_ROTATE"] and panel_id:
                api_payload["PanelId"] = panel_id

            if command == "AUTO_ROTATE":
                api_payload["State"] = state

            if command == "ROTATE":
                if vertical_position is not None and horizontal_position is not None:
                    api_payload["VerticalPosition"] = vertical_position
                    api_payload["HorizontalPosition"] = horizontal_position
                else:
                    return JsonResponse({"status": "error", "message": "Для поворота панели необходимо указать координаты — вертикальную и горизонтальную позиции."}, status=400)

            response = requests.post(EXTERNAL_API_URL, json=api_payload, headers=headers)

            if response.status_code == 200:
                try:
                    api_response_data = response.json()
                    sync_latest_panel_data_to_main_models(request)
                    return JsonResponse({"status": "success", "Команда успешно отправлена. Устройство дало ответ.": api_response_data})
                except json.JSONDecodeError:
                    sync_latest_panel_data_to_main_models(request)
                    return JsonResponse({"status": "success", "message": "Команда отправлена, но ответ от устройства не удалось разобрать."})
            else:
                try:
                    api_response_data = response.json()
                    return JsonResponse({"status": "error", "message": f"Устройство вернуло ошибку (код {response.status_code})."}, status=response.status_code)
                except json.JSONDecodeError:
                    return JsonResponse({"status": "error", "message": f"Устройство вернуло ошибку (код {response.status_code}), но ответ не удалось разобрать."}, status=response.status_code)


        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Ошибка: не удалось обработать данные. Проверьте формат и попробуйте снова."}, status=400)
        except requests.exceptions.RequestException as e:
            return JsonResponse({"status": "error", "message": f"Не удалось установить соединение с устройством. Проверьте подключение и повторите попытку."}, status=500)
        except Exception as e:
            return JsonResponse({"status": "error", "message": f"Произошла непредвиденная ошибка. Пожалуйста, повторите попытку позже."}, status=500)
        
  
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

@method_decorator(superuser_access_required, name='dispatch')
@method_decorator(login_required, name='dispatch')
class CreateHubView(View):
    template_name = 'create_hub.html'
    secondary_alias = 'solar_panel_db'

    def get(self, request):
        form = HubForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = HubForm(request.POST)
        
        panel_errors = []
        panels_data = []

        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        id_hub = form.cleaned_data['id_hub']
        ip = form.cleaned_data['ip_address']
        port = form.cleaned_data['port']

        total_panels = int(request.POST.get('total_panels', 0))
        if total_panels == 0:
            form.add_error(None, "Необходимо добавить хотя бы одну солнечную панель.")
            return render(request, self.template_name, {'form': form})
        
        for i in range(total_panels):
            panel_prefix = f'panel-{i}-'
            panel_id = request.POST.get(panel_prefix + 'id_panel')
            coordinates = request.POST.get(panel_prefix + 'coordinates')
            panel_type = request.POST.get(panel_prefix + 'type')

            panel_data_for_form = {
                'id_panel': panel_id,
                'coordinates': coordinates,
                'type': panel_type,
            }
            panel_form = PanelInlineForm(panel_data_for_form)

            if panel_form.is_valid():
                panels_data.append(panel_form.cleaned_data)
            else:
                for field, errors in panel_form.errors.items():
                    for error in errors:
                        panel_errors.append(f"Панель #{i+1} ({panel_data_for_form.get('id_panel', 'N/A')}) - {panel_form.fields[field].label}: {error}")
        
        if panel_errors:
            form.add_error(None, "Обнаружены ошибки в данных солнечных панелей:")
            for error_msg in panel_errors:
                form.add_error(None, error_msg)
            return render(request, self.template_name, {'form': form})

        try:
            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO hub (id_hub, ip_address, port)
                        VALUES (%s, %s, %s)
                        """, [id_hub, ip, port]
                    )
                    for p_data in panels_data:
                        cursor.execute(
                            """
                            INSERT INTO id_panel (id_panel, type, id_hub)
                            VALUES (%s, %s, %s)
                            """, [p_data['id_panel'], p_data['type'], id_hub]
                        )
            logger.info(f"Hub '{id_hub}' and {len(panels_data)} panels successfully added to secondary DB (without coordinates).")
        except (ProgrammingError, OperationalError, IntegrityError) as e:
            logger.exception(f"Secondary DB write failed for hub '{id_hub}': {e}")
            error_message = f"Ошибка при сохранении во вторичную БД. Возможно, хаб или панель с таким ID уже существует в данном хабе: {e}"
            form.add_error(None, error_message)
            return render(request, self.template_name, {'form': form})
        except Exception as e:
            logger.exception(f"Unexpected error during secondary DB write for hub '{id_hub}': {e}")
            form.add_error(None, f"Неожиданная ошибка при сохранении во вторичную БД: {e}")
            return render(request, self.template_name, {'form': form})

        try:
            with transaction.atomic():
                hub_obj, hub_created = Hub.objects.get_or_create(
                    id_hub=id_hub,
                    defaults={'ip_address': ip, 'port': port}
                )
                if hub_created:
                    logger.info(f"Created Hub in primary DB: {id_hub}")
                else:
                    logger.warning(f"Hub '{id_hub}' already exists in primary DB, updating if necessary.")
                    hub_obj.ip_address = ip
                    hub_obj.port = port
                    hub_obj.save()

                for p_data in panels_data:
                    panel_obj, panel_created = Panel.objects.get_or_create(
                        id_panel=p_data['id_panel'],
                        hub=hub_obj,
                        defaults={'type': p_data['type'], 'coordinates': p_data['coordinates']}
                    )
                    if panel_created:
                        logger.info(f"Created Panel '{p_data['id_panel']}' in primary DB for Hub '{id_hub}' (with coordinates).")
                    else:
                        logger.warning(f"Panel '{p_data['id_panel']}' already exists in primary DB for Hub '{id_hub}', updating if necessary.")
                        panel_obj.type = p_data['type']
                        panel_obj.coordinates = p_data['coordinates']
                        panel_obj.save()

            logger.info(f"Hub '{id_hub}' and associated panels successfully mirrored to primary DB.")
            return redirect('hub_list')

        except IntegrityError as e:
            logger.exception(f"Primary DB write failed due to data integrity for hub '{id_hub}': {e}")
            form.add_error(None, f"Ошибка целостности данных в основной БД. Возможно, панель с таким именем уже существует для этого хаба: {e}")
            return render(request, self.template_name, {'form': form})
        except Exception as e:
            logger.exception(f"Unexpected error during primary DB mirror for hub '{id_hub}': {e}")
            form.add_error(None, f"Неожиданная ошибка при зеркалировании в основную БД: {e}")
            return render(request, self.template_name, {'form': form})


@method_decorator(staff_member_required, name='dispatch')
class HubListView(View):
    template_name = 'hub_list.html'

    def get(self, request):
        hubs = Hub.objects.all().order_by('id_hub')
        return render(request, self.template_name, {'hubs': hubs})


@method_decorator(staff_member_required, name='dispatch')
class HubUpdateView(View):
    template_name = 'hub_edit.html'
    secondary_alias = 'solar_panel_db'

    def get(self, request, pk):
        hub = get_object_or_404(Hub, pk=pk)
        
        form = HubForm(initial={
            'id_hub': hub.id_hub,
            'ip_address': hub.ip_address,
            'port': hub.port,
        }, instance=hub)

        return render(request, self.template_name, {'form': form, 'hub': hub})

    def post(self, request, pk):
        hub_obj = get_object_or_404(Hub, pk=pk)
        form = HubForm(request.POST, instance=hub_obj)
        
        panel_errors = []
        panels_data = []

        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'hub': hub_obj})

        new_id_hub = form.cleaned_data['id_hub']
        new_ip = form.cleaned_data['ip_address']
        new_port = form.cleaned_data['port']

        total_panels = int(request.POST.get('total_panels', 0))
        for i in range(total_panels):
            panel_prefix = f'panel-{i}-'
            panel_id = request.POST.get(panel_prefix + 'id_panel')
            coordinates = request.POST.get(panel_prefix + 'coordinates')
            panel_type = request.POST.get(panel_prefix + 'type')

            panel_data_for_form = {
                'id_panel': panel_id,
                'coordinates': coordinates,
                'type': panel_type,
            }
            panel_form = PanelInlineForm(panel_data_for_form)

            if panel_form.is_valid():
                panels_data.append(panel_form.cleaned_data)
            else:
                for field, errors in panel_form.errors.items():
                    for error in errors:
                        panel_errors.append(f"Панель #{i+1} ({panel_data_for_form.get('id_panel', 'N/A')}) - {panel_form.fields[field].label}: {error}")
        
        if panel_errors:
            form.add_error(None, "Обнаружены ошибки в данных солнечных панелей:")
            for error_msg in panel_errors:
                form.add_error(None, error_msg)
            return render(request, self.template_name, {'form': form, 'hub': hub_obj})

        existing_panels = list(hub_obj.panel_set.all())
        existing_panels_map = {p.id_panel: p for p in existing_panels}
        
        submitted_panel_ids = {p_data['id_panel'] for p_data in panels_data}

        panels_to_create = []
        panels_to_update = []
        panels_to_delete_ids = []

        for p_data in panels_data:
            panel_id = p_data['id_panel']
            if panel_id in existing_panels_map:
                existing_panel = existing_panels_map[panel_id]
                if (existing_panel.coordinates != p_data['coordinates'] or
                    existing_panel.type != p_data['type']):
                    panels_to_update.append((existing_panel, p_data))
            else:
                panels_to_create.append(p_data)

        for existing_panel_obj in existing_panels:
            if existing_panel_obj.id_panel not in submitted_panel_ids:
                panels_to_delete_ids.append(existing_panel_obj.id_panel)

        try:
            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE hub
                        SET ip_address = %s, port = %s, id_hub = %s
                        WHERE id_hub = %s
                        """, [new_ip, new_port, new_id_hub, hub_obj.id_hub]
                    )
                    if new_id_hub != hub_obj.id_hub:
                        cursor.execute(
                            """
                            UPDATE id_panel
                            SET id_hub = %s
                            WHERE id_hub = %s
                            """, [new_id_hub, hub_obj.id_hub]
                        )
                    
                    if panels_to_delete_ids:
                        placeholders = ','.join(['%s'] * len(panels_to_delete_ids))
                        cursor.execute(
                            f"""
                            DELETE FROM panel_data
                            WHERE id_hub = %s AND id_panel IN ({placeholders})
                            """, [new_id_hub, *panels_to_delete_ids]
                        )
                        cursor.execute(
                            f"""
                            DELETE FROM id_panel
                            WHERE id_hub = %s AND id_panel IN ({placeholders})
                            """, [new_id_hub, *panels_to_delete_ids]
                        )
                        logger.info(f"Deleted panels {panels_to_delete_ids} from secondary DB for hub '{new_id_hub}'.")

                    for p_data in panels_to_create:
                        cursor.execute(
                            """
                            INSERT INTO id_panel (id_panel, type, id_hub)
                            VALUES (%s, %s, %s)
                            """, [p_data['id_panel'], p_data['type'], new_id_hub]
                        )
                        logger.info(f"Added new panel '{p_data['id_panel']}' to secondary DB for hub '{new_id_hub}'.")

                    for existing_panel, p_data in panels_to_update:
                        cursor.execute(
                            """
                            UPDATE id_panel
                            SET type = %s
                            WHERE id_panel = %s AND id_hub = %s
                            """, [p_data['type'], p_data['id_panel'], new_id_hub]
                        )
                        logger.info(f"Updated panel '{p_data['id_panel']}' in secondary DB for hub '{new_id_hub}'.")
            
            logger.info(f"Hub '{hub_obj.id_hub}' (now '{new_id_hub}') and associated panels successfully updated in secondary DB.")
        except (ProgrammingError, OperationalError, IntegrityError) as e:
            logger.exception(f"Secondary DB update failed for hub '{hub_obj.id_hub}': {e}")
            form.add_error(None, f"Ошибка при обновлении во вторичную БД: {e}. Возможно, вы пытаетесь добавить панель с уже существующим именем в этот хаб.")
            return render(request, self.template_name, {'form': form, 'hub': hub_obj})
        except Exception as e:
            logger.exception(f"Unexpected error during secondary DB update for hub '{hub_obj.id_hub}': {e}")
            form.add_error(None, f"Неожиданная ошибка при обновлении во вторичную БД: {e}")
            return render(request, self.template_name, {'form': form, 'hub': hub_obj})


        try:
            with transaction.atomic():
                hub_obj.id_hub = new_id_hub
                hub_obj.ip_address = new_ip
                hub_obj.port = new_port
                hub_obj.save()
                logger.info(f"Hub '{hub_obj.id_hub}' successfully updated in primary DB.")

                if panels_to_delete_ids:
                    Panel.objects.filter(hub=hub_obj, id_panel__in=panels_to_delete_ids).delete()
                    logger.info(f"Deleted panels {panels_to_delete_ids} from primary DB for hub '{new_id_hub}'.")

                for p_data in panels_to_create:
                    Panel.objects.create(
                        hub=hub_obj,
                        id_panel=p_data['id_panel'],
                        coordinates=p_data['coordinates'],
                        type=p_data['type']
                    )
                    logger.info(f"Created new panel '{p_data['id_panel']}' in primary DB for hub '{new_id_hub}'.")

                for existing_panel, p_data in panels_to_update:
                    existing_panel.coordinates = p_data['coordinates']
                    existing_panel.type = p_data['type']
                    existing_panel.save()
                    logger.info(f"Updated panel '{p_data['id_panel']}' in primary DB for hub '{new_id_hub}'.")

            return redirect('hub_list')

        except IntegrityError as e:
            logger.exception(f"Primary DB update failed due to data integrity for hub '{hub_obj.id_hub}': {e}")
            form.add_error(None, f"Ошибка целостности данных в основной БД. Возможно, панель с таким именем уже существует для этого хаба: {e}")
            return render(request, self.template_name, {'form': form, 'hub': hub_obj})
        except Exception as e:
            logger.exception(f"Primary DB update mirror failed for hub '{hub_obj.id_hub}': {e}")
            form.add_error(None, f"Ошибка при зеркалировании обновления в основную БД: {e}")
            return render(request, self.template_name, {'form': form, 'hub': hub_obj})


@method_decorator(staff_member_required, name='dispatch')
class HubDeleteView(View):
    template_name = 'hub_confirm_delete.html'
    secondary_alias = 'solar_panel_db'

    def get(self, request, pk):
        hub = get_object_or_404(Hub, pk=pk)
        return render(request, self.template_name, {'hub': hub})

    def post(self, request, pk):
        hub = get_object_or_404(Hub, pk=pk)

        # --- Архивирование данных панелей перед удалением ---
        try:
            if not os.path.exists(ARCHIVE_DIR):
                os.makedirs(ARCHIVE_DIR)

            archive_filename = f"hub_{hub.id_hub}_panel_data_archive_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
            archive_filepath = os.path.join(ARCHIVE_DIR, archive_filename)

            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            pd.id_panel_data,
                            pd.value,
                            pd.timestamp,
                            ip.id_panel,
                            ip.type AS panel_type,
                            h.id_hub,
                            h.ip_address,
                            h.port
                        FROM
                            panel_data pd
                        JOIN
                            id_panel ip ON pd.id_panel = ip.id_panel AND pd.id_hub = ip.id_hub
                        JOIN
                            hub h ON ip.id_hub = h.id_hub
                        WHERE
                            h.id_hub = %s;
                        """, [hub.id_hub]
                    )
                    panel_data_records = cursor.fetchall()

            if panel_data_records:
                with open(archive_filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['id_panel_data', 'value', 'timestamp', 'id_panel', 'panel_type', 'id_hub', 'ip_address', 'port'])
                    writer.writerows(panel_data_records)
                logger.info(f"Archived {len(panel_data_records)} panel data records for hub '{hub.id_hub}' to '{archive_filepath}'.")
            else:
                logger.info(f"No panel data records to archive for hub '{hub.id_hub}'.")

        except (ProgrammingError, OperationalError) as e:
            logger.exception(f"Error archiving panel data for hub '{hub.id_hub}': {e}. Proceeding with deletion.")
        except Exception as e:
            logger.exception(f"Unexpected error during panel data archiving for hub '{hub.id_hub}': {e}. Proceeding with deletion.")

        # --- Удаление во вторичной БД (прямые SQL запросы) ---
        try:
            with transaction.atomic(using=self.secondary_alias):
                conn = connections[self.secondary_alias]
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id_panel FROM id_panel
                        WHERE id_hub = %s
                        """, [hub.id_hub]
                    )
                    panel_ids_to_delete = [row[0] for row in cursor.fetchall()]

                    if panel_ids_to_delete:
                        placeholders = ','.join(['%s'] * len(panel_ids_to_delete))
                        cursor.execute(
                            f"""
                            DELETE FROM panel_data
                            WHERE id_hub = %s AND id_panel IN ({placeholders})
                            """, [hub.id_hub, *panel_ids_to_delete]
                        )
                        logger.info(f"Deleted PanelData for {len(panel_ids_to_delete)} panels of Hub '{hub.id_hub}' from secondary DB.")

                    cursor.execute(
                        """
                        DELETE FROM id_panel
                        WHERE id_hub = %s
                        """, [hub.id_hub]
                    )
                    logger.info(f"Deleted Panels for Hub '{hub.id_hub}' from secondary DB.")

                    cursor.execute(
                        """
                        DELETE FROM hub
                        WHERE id_hub = %s
                        """, [hub.id_hub]
                    )
                    logger.info(f"Hub '{hub.id_hub}' successfully deleted from secondary DB.")
        except (ProgrammingError, OperationalError) as e:
            logger.exception(f"Secondary DB deletion failed for hub '{hub.id_hub}': {e}")
            return render(request, self.template_name, {'hub': hub, 'error': f"Ошибка при удалении из вторичной БД: {e}"})
        except Exception as e:
            logger.exception(f"Unexpected error during secondary DB deletion for hub '{hub.id_hub}': {e}")
            return render(request, self.template_name, {'hub': hub, 'error': f"Неожиданная ошибка при удалении из вторичной БД: {e}"})

        # --- Удаление в основной БД (Django ORM) ---
        try:
            with transaction.atomic():
                # Проверяем, есть ли панели, связанные с этим хабом
                panels_count = hub.panel_set.count()
                if panels_count > 0:
                    panel_ids = list(hub.panel_set.values_list('id_panel', flat=True))
                    hub.panel_set.all().delete()
                    logger.info(f"Deleted {panels_count} panels ({panel_ids}) for Hub '{hub.id_hub}' from primary DB before hub deletion.")
                else:
                    logger.info(f"No panels found for Hub '{hub.id_hub}' in primary DB to delete before hub deletion.")
                
                hub.delete()
            logger.info(f"Hub '{hub.id_hub}' successfully deleted from primary DB.")
            return redirect('hub_list')
        except Exception as e:
            logger.exception(f"Primary DB deletion mirror failed for hub '{hub.id_hub}': {e}")
            return render(request, self.template_name, {'hub': hub, 'error': f"Ошибка при зеркалировании удаления в основную БД: {e}"})
