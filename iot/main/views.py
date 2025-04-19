from datetime import datetime
import time
from django.views.generic import View
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from .models import Solar_Panel, Characteristics, Hub, Panel, PanelData
from django.views.decorators.csrf import csrf_exempt
from django.core import serializers
import requests
import json
from django.template.defaultfilters import date
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import plotly.express as px
import pandas as pd
from django.utils.decorators import method_decorator
import os
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import SolarPanelSerializer, CharacteristicsSerializer
from datetime import timedelta
from django.utils import timezone

EXTERNAL_API_URL = "http://your-external-api-server.com/api/command"  # Замени на URL API

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
                'lat': panel.lat if hasattr(panel, 'lat') else None,
                'lng': panel.lng if hasattr(panel, 'lng') else None, 
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

            response = requests.post(EXTERNAL_API_URL, json=api_payload)

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