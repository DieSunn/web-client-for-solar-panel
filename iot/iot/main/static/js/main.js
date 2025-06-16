const body = document.querySelector("body"),
  sidebar = body.querySelector(".sidebar"),
  main_content = body.querySelector(".main-content"),
  modeSwitch = body.querySelector(".toggle-switch"),
  modeText = body.querySelector(".mode-text"),
  toggle = body.querySelector(".toggle");

modeSwitch.addEventListener("click", () => {
  if (getCookie("night_mode") === "on") {
    body.classList.toggle("dark");
    setCookie("night_mode", "off");
  } else {
    body.classList.toggle("dark");
    setCookie("night_mode", "on");
  }
});

toggle.addEventListener("click", () => {
  sidebar.classList.toggle("close");
  main_content.classList.toggle("close");
});

//
function setCookie(name, value, options = {}) {
  options = {
    path: "/",
    // при необходимости добавьте другие значения по умолчанию
    ...options,
  };

  if (options.expires instanceof Date) {
    options.expires = options.expires.toUTCString();
  }

  let updatedCookie =
    encodeURIComponent(name) + "=" + encodeURIComponent(value);

  for (let optionKey in options) {
    updatedCookie += "; " + optionKey;
    let optionValue = options[optionKey];
    if (optionValue !== true) {
      updatedCookie += "=" + optionValue;
    }
  }

  document.cookie = updatedCookie;
}

// Геттер куки для режима ночного режима
function getCookie(name) {
  let matches = document.cookie.match(
    new RegExp(
      "(?:^|; )" +
        name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, "\\$1") +
        "=([^;]*)"
    )
  );
  return matches ? decodeURIComponent(matches[1]) : undefined;
}

function checkCookie() {
  let status = getCookie("night_mode");
  if (status === "on") {
    body.classList.toggle("dark");
  }
}


document.addEventListener('DOMContentLoaded', function() {
    // --- Existing sidebar and mode logic ---
    const body = document.querySelector("body");
    const sidebar = body.querySelector(".sidebar");
    const toggle = body.querySelector(".toggle");
    const modeSwitch = body.querySelector(".toggle-switch");
    const modeText = body.querySelector(".mode-text");

    // Load initial state
    const nightMode = localStorage.getItem('nightMode');
    if (nightMode === 'on') {
        body.classList.add('dark');
    } else {
        body.classList.remove('dark');
    }

    toggle.addEventListener("click", () => {
        sidebar.classList.toggle("close");
        // Adjust main content margin
        const mainContent = document.querySelector('.main-content');
        if (sidebar.classList.contains('close')) {
            mainContent.style.marginLeft = '78px';
        } else {
            mainContent.style.marginLeft = '250px';
        }
    });

    modeSwitch.addEventListener("click", () => {
        body.classList.toggle("dark");
        if (body.classList.contains("dark")) {
            localStorage.setItem('nightMode', 'on');
        } else {
            localStorage.setItem('nightMode', 'off');
        }
    });

    // Initial adjustment for main content
    const mainContent = document.querySelector('.main-content');
    if (sidebar.classList.contains('close')) {
        mainContent.style.marginLeft = '78px';
    } else {
        mainContent.style.marginLeft = '250px';
    }


    // --- New: Sync Panels Button Logic ---
    const syncLink = document.getElementById('syncPanelsButton'); // Target the <a> element
    
    // Ensure the syncLink exists and is within the staff user block
    if (syncLink) {
        const syncTextSpan = syncLink.querySelector('.nav-text'); // Get the span for text changes
        const syncIcon = syncLink.querySelector('.icon'); // Get the icon for animation

        syncLink.addEventListener('click', function(event) {
            event.preventDefault(); // Prevent default link behavior (navigating)

            // Disable the link visually and functionally
            syncLink.style.pointerEvents = 'none'; // Prevents clicks
            syncLink.style.opacity = '0.7'; // Visual dimming

            // Update text and icon for feedback
            if (syncTextSpan) {
                syncTextSpan.textContent = 'Обновление...';
            }
            if (syncIcon) {
                syncIcon.classList.remove('bx-refresh'); // Remove original icon
                syncIcon.classList.add('bx-loader-alt', 'bx-spin'); // Add spinning loader icon
            }

            // Make the API call
            fetch('/api/sync-panel-data/', {
                method: 'POST', // Use POST for data updates
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') // Important for Django POST requests
                },
                // body: JSON.stringify({}) // Include body if your API expects data, though not strictly needed for a simple sync trigger
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok: ' + response.statusText);
                }
                return response.json(); // Assuming your API returns JSON
            })
            .then(data => {
                console.log('Данные успешно обновлены:', data);
                alert('Данные панелей успешно обновлены!'); // User feedback
            })
            .catch(error => {
                console.error('Ошибка при обновлении данных:', error);
                alert('Произошла ошибка при обновлении данных. Смотрите консоль для подробностей.'); // User feedback on error
            })
            .finally(() => {
                // Re-enable the link and reset text/icon
                syncLink.style.pointerEvents = 'auto';
                syncLink.style.opacity = '1';

                if (syncTextSpan) {
                    syncTextSpan.textContent = 'Обновить данные';
                }
                if (syncIcon) {
                    syncIcon.classList.remove('bx-loader-alt', 'bx-spin'); // Remove loader
                    syncIcon.classList.add('bx-refresh'); // Restore original icon
                }
            });
        });
    }
});