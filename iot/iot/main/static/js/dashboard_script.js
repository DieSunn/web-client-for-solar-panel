$(function() {
    // --- Переменные DOM-элементов ---
    const dayBtn = $('#dayBtn');
    const weekBtn = $('#weekBtn');
    const monthBtn = $('#monthBtn');
    const dateRangeInput = $('#dateRangeInput');
    const timeFilter = $('#timeFilter');
    const exportBtn = $('#exportData');
    const overallBtn = $('#showOverallStats');
    const nightModeSwitch = $('#nightModeSwitch'); // Чекбокс в заголовке (для проверки состояния)
    const openMapModalBtn = $('#openMapModalBtn');
    const mapModal = $('#mapModal');
    const closeModalBtn = $('.close-modal-btn');
    const modalTabs = $('.modal-tabs .tab-link');
    const modalPanelList = $('#modalPanelList');
    const selectedPanelNameDisplay = $('#selectedPanelName');
    const chartLoaders = $('.chart-loader');

    let currentData = null;
    let modalMapInstance = null;
    let markers = {};
    let solarPanelData = [];
    let selectedPanelId = 'all'; // Храним ID выбранной панели, по умолчанию 'all'

    // --- Инициализация Chart.js ---
    const powerCtx = $('#powerChart')[0].getContext('2d');
    const powerChart = new Chart(powerCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'Генерация', data: [], borderColor: 'rgba(109, 212, 126, 1)', backgroundColor: 'rgba(109, 212, 126, 0.2)', fill: true, tension: 0.3, pointRadius: 2, pointHoverRadius: 5 },
                { label: 'Потребление', data: [], borderColor: 'rgba(74, 144, 226, 1)', backgroundColor: 'rgba(74, 144, 226, 0.2)', fill: true, tension: 0.3, pointRadius: 2, pointHoverRadius: 5 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 15,
                        usePointStyle: true,
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    borderWidth: 1,
                    cornerRadius: 8,
                    displayColors: true,
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Время' },
                    ticks: { maxRotation: 0, minRotation: 0, autoSkip: true, maxTicksLimit: 10 },
                    grid: {}
                },
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Мощность (кВт)' },
                    ticks: {},
                    grid: {}
                }
            }
        }
    });

    const effCtx = $('#efficiencyChart')[0].getContext('2d');
    const effChart = new Chart(effCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'Эффективность', data: [], borderColor: 'rgba(100, 181, 246, 1)', backgroundColor: 'rgba(100, 181, 246, 0.2)', fill: true, tension: 0.3, pointRadius: 2, pointHoverRadius: 5 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `Эффективность: ${ctx.raw}%`
                    },
                    borderWidth: 1,
                    cornerRadius: 8,
                    displayColors: false,
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Время' },
                    ticks: { maxRotation: 0, minRotation: 0, autoSkip: true, maxTicksLimit: 10 },
                    grid: {}
                },
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Эффективность (%)' },
                    ticks: { callback: v => v + '%' },
                    grid: {}
                }
            }
        }
    });

    // Функция для обновления цветов графиков при смене темы
    window.updateChartColorsAndMarkers = function(isNightModeActive) {
        // Цвета для светлой темы
        const lightColors = {
            legendColor: '#333333',
            tooltipBg: 'rgba(0, 0, 0, 0.8)',
            tooltipBorder: 'rgba(0, 0, 0, 0.9)',
            axisColor: '#666666',
            tickColor: '#999999',
            gridColor: 'rgba(0, 0, 0, 0.05)',
            leafletFill: '#4A90E2',
            leafletStroke: '#000'
        };

        // Цвета для темной темы
        const darkColors = {
            legendColor: '#BDC3C7',
            tooltipBg: 'rgba(52, 73, 94, 0.9)',
            tooltipBorder: 'rgba(74, 97, 121, 0.9)',
            axisColor: '#BDC3C7',
            tickColor: '#95A5A6',
            gridColor: 'rgba(74, 97, 121, 0.3)',
            leafletFill: '#42A5F5',
            leafletStroke: '#CCC'
        };

        const colors = isNightModeActive ? darkColors : lightColors;

        // Обновление powerChart
        powerChart.options.plugins.legend.labels.color = colors.legendColor;
        powerChart.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
        powerChart.options.plugins.tooltip.borderColor = colors.tooltipBorder;
        powerChart.options.scales.x.title.color = colors.axisColor;
        powerChart.options.scales.x.ticks.color = colors.tickColor;
        powerChart.options.scales.x.grid.color = colors.gridColor;
        powerChart.options.scales.y.title.color = colors.axisColor;
        powerChart.options.scales.y.ticks.color = colors.tickColor;
        powerChart.options.scales.y.grid.color = colors.gridColor;

        // Обновление effChart
        effChart.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
        effChart.options.plugins.tooltip.borderColor = colors.tooltipBorder;
        effChart.options.scales.x.title.color = colors.axisColor;
        effChart.options.scales.x.ticks.color = colors.tickColor;
        effChart.options.scales.x.grid.color = colors.gridColor;
        effChart.options.scales.y.title.color = colors.axisColor;
        effChart.options.scales.y.ticks.color = colors.tickColor;
        effChart.options.scales.y.grid.color = colors.gridColor;

        powerChart.update();
        effChart.update();

        // Обновляем маркеры Leaflet, если карта инициализирована
        if (modalMapInstance) {
            updateMapMarkers(colors.leafletFill, colors.leafletStroke);
        }
    };

    // Вызываем обновление цветов при первой загрузке (если тема уже установлена)
    updateChartColorsAndMarkers($('body').hasClass('dark'));


    // --- Функции ---

    // Показ/скрытие индикатора загрузки
    function showLoading() {
        chartLoaders.fadeIn(200);
    }
    function hideLoading() {
        chartLoaders.fadeOut(200);
    }

    // Установка активной кнопки периода
    function setActivePeriodButton(btn) {
        $('.btn-group .btn').removeClass('active');
        if (btn) {
            btn.addClass('active');
        }
        dateRangeInput.val(''); // Сбрасываем значение DateRangePicker
    }

    // Обновление статистики
    function updateStats(gen, cons, eff) {
        const avg = arr => arr.length ? (arr.reduce((s,v)=>s+Number(v),0)/arr.length).toFixed(2) : '–';
        const max = arr => arr.length ? Math.max(...arr.map(Number)).toFixed(2) : '–';
        const min = arr => arr.length ? Math.min(...arr.map(Number)).toFixed(2) : '–';

        $('#avgGeneration').text(avg(gen));
        $('#maxGeneration').text(max(gen));
        $('#minGeneration').text(min(gen));

        $('#avgConsumption').text(avg(cons));
        $('#maxConsumption').text(max(cons));
        $('#minConsumption').text(min(cons));

        const validEff = eff.filter(e => typeof e === 'number' && !isNaN(e));
        $('#avgEfficiency').text(avg(validEff));
        $('#peakEfficiency').text(max(validEff));
    }

    // Показ сообщения об ошибке (кастомный модальный стиль)
    function showError(msg) {
        const errorDiv = $('<div class="error-message"></div>');
        errorDiv.html(`<span>${msg}</span><button class="close-error">&times;</button>`);
        $('.dashboard-container').prepend(errorDiv);
        errorDiv.find('.close-error').on('click', function() {
            $(this).closest('.error-message').fadeOut(300, function() {
                $(this).remove();
            });
        });
        setTimeout(() => {
            errorDiv.fadeOut(500, function() {
                $(this).remove();
            });
        }, 5000);
    }

    // Обновление графиков и статистики
    function updateDashboard(data) {
        currentData = data;
        if (!data || !data.date || data.date.length === 0) {
            powerChart.data.labels = [];
            powerChart.data.datasets[0].data = [];
            powerChart.data.datasets[1].data = [];
            powerChart.update();
            effChart.data.labels = [];
            effChart.data.datasets[0].data = [];
            effChart.update();
            updateStats([], [], []);
            console.warn("Нет данных для отображения.");
            return;
        }

        // Фильтрация по времени суток
        const timeFilterValue = timeFilter.val();
        const filteredIndices = data.date.map((d, i) => {
            const hour = moment(d).hour();
            const ranges = { morning: [6, 12], afternoon: [12, 18], evening: [18, 24], night: [0, 6] };
            const isInRange = timeFilterValue === 'all' ||
                              (timeFilterValue === 'night' ? (hour >= ranges.night[0] || hour < ranges.night[1]) :
                              (hour >= ranges[timeFilterValue][0] && hour < ranges[timeFilterValue][1]));
            return isInRange ? i : null;
        }).filter(i => i !== null);

        const dates = filteredIndices.map(i => moment(data.date[i]).format('DD.MM HH:mm'));
        const gen = filteredIndices.map(i => parseFloat(data.generated_power[i]));
        const cons = filteredIndices.map(i => parseFloat(data.consumed_power[i]));
        const eff = gen.map((g, index) => {
            const c = cons[index];
            if (typeof g === 'number' && typeof c === 'number' && g > 0) {
                const efficiencyValue = (c / g) * 100;
                return parseFloat(Math.min(efficiencyValue, 100).toFixed(1));
            }
            return 0;
        });

        powerChart.data.labels = dates;
        powerChart.data.datasets[0].data = gen;
        powerChart.data.datasets[1].data = cons;
        powerChart.update();

        effChart.data.labels = dates;
        effChart.data.datasets[0].data = eff;
        effChart.update();

        updateStats(gen, cons, eff);
    }

    // Получение данных с сервера
    function fetchData(params = {}) {
        showLoading();
        if (selectedPanelId !== 'all') {
            params.panel_id = selectedPanelId;
        } else {
            delete params.panel_id;
        }

        // Имитация запроса к API. В реальном приложении:
        $.getJSON('/get-general-characteristics-data/', params)
            .done(updateDashboard)
            .fail(() => showError('Не удалось загрузить данные характеристик'))
            .always(hideLoading);

        // --- Заглушка для демонстрации без реального бэкенда ---
        /*
        const mockData = generateMockData(params);
        setTimeout(() => {
            updateDashboard(mockData);
            hideLoading();
        }, 800);
        */
        // --- Конец заглушки ---
    }

    // Функция для генерации моковых данных (для тестирования без бэкенда)
    function generateMockData(params) {
        const dates = [];
        const generated_power = [];
        const consumed_power = [];
        let startDate, endDate, interval;

        if (params.range === 'day') {
            startDate = moment().subtract(1, 'days').startOf('day');
            endDate = moment().subtract(1, 'days').endOf('day');
            interval = 'hour';
        } else if (params.range === 'week') {
            startDate = moment().subtract(7, 'days').startOf('day');
            endDate = moment().endOf('day');
            interval = 'day';
        } else if (params.range === 'month') {
            startDate = moment().subtract(30, 'days').startOf('day');
            endDate = moment().endOf('day');
            interval = 'day';
        } else if (params.start_date && params.end_date) {
            startDate = moment(params.start_date, 'YYYY-MM-DD').startOf('day');
            endDate = moment(params.end_date, 'YYYY-MM-DD').endOf('day');
            const diffDays = endDate.diff(startDate, 'days');
            if (diffDays <= 2) interval = 'hour';
            else if (diffDays <= 30) interval = 'day';
            else interval = 'week';
        } else {
            startDate = moment().subtract(1, 'days').startOf('day');
            endDate = moment().subtract(1, 'days').endOf('day');
            interval = 'hour';
        }

        let current = moment(startDate);
        while (current.isSameOrBefore(endDate)) {
            dates.push(current.toISOString());
            const gen = (Math.random() * 50) + 20; // 20-70 кВт
            const cons = (Math.random() * 30) + 10; // 10-40 кВт
            generated_power.push(parseFloat(gen.toFixed(2)));
            consumed_power.push(parseFloat(cons.toFixed(2)));

            if (interval === 'hour') current.add(1, 'hour');
            else if (interval === 'day') current.add(1, 'day');
            else if (interval === 'week') current.add(1, 'week');
        }
        return { date: dates, generated_power, consumed_power };
    }


    // Инициализация карты Leaflet в модальном окне
    function initializeModalMap() {
        if (!modalMapInstance) {
            modalMapInstance = L.map('modalMap').setView([55.7558, 37.6173], 5);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }).addTo(modalMapInstance);
        }
        // Обновляем маркеры при каждом открытии/переключении на карту
        const isNightModeActive = $('body').hasClass('dark');
        const colors = isNightModeActive ? {leafletFill: '#42A5F5', leafletStroke: '#CCC'} : {leafletFill: '#4A90E2', leafletStroke: '#000'};
        updateMapMarkers(colors.leafletFill, colors.leafletStroke);

        // Важно: обновить размер карты после того, как контейнер станет видимым
        setTimeout(() => {
            if (modalMapInstance) {
                modalMapInstance.invalidateSize();
            }
        }, 100);
    }

    // Обновление маркеров на карте (принимает цвета)
    function updateMapMarkers(fillColor, strokeColor) {
        if (!modalMapInstance) return;

        Object.values(markers).forEach(marker => marker.remove());
        markers = {};

        solarPanelData.forEach(p => {
            if (p.lat != null && p.lng != null) {
                const marker = L.circleMarker([p.lat, p.lng], {
                    radius: 8, fillColor: fillColor, color: strokeColor,
                    weight: 1, opacity: 1, fillOpacity: 0.8
                }).addTo(modalMapInstance)
                  .bindPopup(`<b>ID Панели:</b> ${p.id_panel}<br><b>Хаб:</b> ${p.hub_id || 'N/A'}`);

                marker.on('click', () => {
                    selectedPanelId = p.id_panel;
                    const panelText = `Панель ${p.id_panel} (Хаб: ${p.hub_id || 'N/A'})`;
                    selectedPanelNameDisplay.text(panelText);
                    mapModal.hide();
                    setActivePeriodButton(dayBtn);
                    fetchData({ range: 'day' });
                });
                markers[p.id_panel] = marker;
            } else {
                console.warn(`Panel ${p.id_panel} is missing coordinates.`);
            }
        });
    }


    // Заполнение списка панелей в модальном окне
    function populatePanelList() {
        modalPanelList.empty();

        const allPanelsItem = $('<li></li>').text('Все панели');
        allPanelsItem.data('panel-id', 'all');
        allPanelsItem.on('click', function() {
            selectedPanelId = $(this).data('panel-id');
            selectedPanelNameDisplay.text('Выбраны: Все панели');
            mapModal.hide();
            setActivePeriodButton(dayBtn);
            fetchData({ range: 'day' });
        });
        modalPanelList.append(allPanelsItem);

        if (solarPanelData.length === 0 && selectedPanelId === 'all') { // Проверка, чтобы не дублировать сообщение
            modalPanelList.append('<li>Нет данных о панелях.</li>');
        }

        solarPanelData.forEach(p => {
            const panelText = `Панель ${p.id_panel} (Хаб: ${p.hub_id || 'N/A'})`;
            const listItem = $('<li></li>').text(panelText);
            listItem.data('panel-id', p.id_panel);
            listItem.on('click', function() {
                const panelId = $(this).data('panel-id');
                selectedPanelId = panelId;
                selectedPanelNameDisplay.text(panelText);
                mapModal.hide();
                setActivePeriodButton(dayBtn);
                fetchData({ range: 'day' });
            });
            modalPanelList.append(listItem);
        });
    }

    // Загрузка данных о панелях (имитация)
    function fetchPanelData() {
        $.getJSON('/solar-panels/') // Ваш реальный API-эндпоинт Django
            .done(data => {
                solarPanelData = data;
                populatePanelList();
            })
            .fail(() => {
                showError('Не удалось загрузить данные о панелях');
                modalPanelList.html('<li>Ошибка загрузки списка.</li>');
                // Добавляем "Все панели" даже при ошибке загрузки остальных
                populatePanelList();
            });

        // --- Заглушка для демонстрации без реального бэкенда ---
        /*
        const mockPanelData = [
            { id_panel: 'SP001', hub_id: 'HUB_A', lat: 55.7558, lng: 37.6173 },
            { id_panel: 'SP002', hub_id: 'HUB_B', lat: 59.9343, lng: 30.3351 },
            { id_panel: 'SP003', hub_id: 'HUB_C', lat: 56.8389, lng: 60.6057 },
            { id_panel: 'SP004', hub_id: 'HUB_A', lat: 55.0302, lng: 82.9204 },
            { id_panel: 'SP005', hub_id: 'HUB_D', lat: 43.1167, lng: 131.8761 },
            { id_panel: 'SP006', hub_id: 'HUB_B', lat: 51.5074, lng: 0.1278 }, // Лондон
            { id_panel: 'SP007', hub_id: 'HUB_C', lat: 40.7128, lng: -74.0060 }, // Нью-Йорк
            { id_panel: 'SP008', hub_id: 'HUB_D', lat: 34.0522, lng: -118.2437 }, // Лос-Анджелес
            { id_panel: 'SP009', hub_id: 'HUB_A', lat: 48.8566, lng: 2.3522 }, // Париж
            { id_panel: 'SP010', hub_id: 'HUB_B', lat: 35.6895, lng: 139.6917 }, // Токио
        ];
        setTimeout(() => {
            solarPanelData = mockPanelData;
            populatePanelList();
        }, 500);
        */
        // --- Конец заглушки ---
    }


    // --- Обработчики событий ---

    // Кнопки выбора периода
    dayBtn.click(() => { setActivePeriodButton(dayBtn); fetchData({ range: 'day' }); });
    weekBtn.click(() => { setActivePeriodButton(weekBtn); fetchData({ range: 'week' }); });
    monthBtn.click(() => { setActivePeriodButton(monthBtn); fetchData({ range: 'month' }); });

    // Выбор диапазона дат вручную
    dateRangeInput.on('apply.daterangepicker', (ev, picker) => {
        setActivePeriodButton(null);
        fetchData({
            start_date: picker.startDate.format('YYYY-MM-DD'),
            end_date: picker.endDate.format('YYYY-MM-DD')
        });
    });

    // Фильтр времени суток
    timeFilter.change(() => {
        if (currentData) {
            updateDashboard(currentData);
        }
    });

    // Экспорт данных
    exportBtn.click(() => {
        if (!currentData || !currentData.date || currentData.date.length === 0) {
            return showError('Нет данных для экспорта');
        }
        const dates = currentData.date, gen = currentData.generated_power, cons = currentData.consumed_power;
        const eff = gen.map((g,i)=> g>0 ? parseFloat(Math.min((cons[i]/g*100), 100).toFixed(1)) : 0);
        let csv = 'Дата;Генерация (кВт);Потребление (кВт);Эффективность (%)\n';
        dates.forEach((d,i)=> csv += `${moment(d).format('DD.MM.YYYY HH:mm')};${gen[i]};${cons[i]};${eff[i]}\n`);

        const BOM = "\uFEFF"; // Byte Order Mark для корректного отображения кириллицы
        const blob = new Blob([BOM + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `data_${moment().format('YYYYMMDD_HHmmss')}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    });

    // Кнопка общей статистики
    overallBtn.click(() => showError('Эта функция еще не реализована. Здесь можно показать общую статистику по всем установкам.'));

    // --- Логика модального окна ---

    // Открытие модального окна
    openMapModalBtn.click(() => {
        mapModal.css('display', 'flex');
        modalTabs.removeClass('active');
        $('.tab-link[data-tab="panelListTab"]').addClass('active');
        $('.tab-content').removeClass('active');
        $('#panelListTab').addClass('active');
    });

    // Закрытие модального окна
    closeModalBtn.click(() => {
        mapModal.css('display', 'none');
    });
    $(window).click(event => {
        if ($(event.target).is(mapModal)) {
            mapModal.css('display', 'none');
        }
    });

    // Переключение вкладок в модальном окне
    modalTabs.click(function() {
        const tabId = $(this).data('tab');

        modalTabs.removeClass('active');
        $(this).addClass('active');

        $('.tab-content').removeClass('active');
        $('#' + tabId).addClass('active');

        if (tabId === 'mapTab') {
            initializeModalMap();
        }
    });

    // Синхронизация Leaflet карты при изменении размера сайдбара
    // Эта функция вызывается из main.js
    // $(window).on('sidebarToggled', function() {
    //     if (mapModal.is(':visible') && $('#mapTab').hasClass('active') && modalMapInstance) {
    //         setTimeout(() => {
    //             modalMapInstance.invalidateSize();
    //         }, 300);
    //     }
    // });


    // --- Первоначальная загрузка данных ---
    fetchPanelData(); // Загружаем данные о панелях (и заполняем список)
    setActivePeriodButton(dayBtn); // Устанавливаем "День" активным по умолчанию
    fetchData({ range: 'day' }); // Загружаем данные для графиков за день (для 'all' панелей)
});
