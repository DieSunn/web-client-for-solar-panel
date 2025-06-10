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

        // РЕАЛЬНЫЙ ЗАПРОС К API Django
        $.getJSON('/get-general-characteristics-data/', params)
            .done(updateDashboard)
            .fail(() => showError('Не удалось загрузить данные характеристик. Проверьте эндпоинт Django.'))
            .always(hideLoading);
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

    // Загрузка данных о панелях
    function fetchPanelData() {
        // РЕАЛЬНЫЙ ЗАПРОС К API Django
        $.getJSON('/solar-panels/')
            .done(data => {
                solarPanelData = data;
                populatePanelList();
            })
            .fail(() => {
                showError('Не удалось загрузить данные о панелях. Проверьте эндпоинт Django.');
                modalPanelList.html('<li>Ошибка загрузки списка.</li>');
                // Добавляем "Все панели" даже при ошибке загрузки остальных
                populatePanelList();
            });
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

    // --- Первоначальная загрузка данных ---
    fetchPanelData(); // Загружаем данные о панелях (и заполняем список)
    setActivePeriodButton(dayBtn); // Устанавливаем "День" активным по умолчанию
    fetchData({ range: 'day' }); // Загружаем данные для графиков за день (для 'all' панелей)
});
