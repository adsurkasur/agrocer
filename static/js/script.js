// =========================
// DEFAULT LOCATION
// =========================
let currentLat = -7.956;
let currentLon = 112.6159;
let locationMessage = "Using your current GPS location.";

// =========================
// CHARTS INSTANCES
// =========================
let tempChart, humChart, luxChart;

// =========================
// INITIALIZATION
// =========================
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    getLocation();
    updateDashboard();

    // Refresh intervals
    setInterval(updateDashboard, 5000); // Updated to 5s to be less aggressive but still real-time
    setInterval(updateLiveClock, 1000);
});

// =========================
// GET LOCATION
// =========================
function getLocation() {
    const locEl = document.getElementById("locationInfo");
    if (!navigator.geolocation) {
        locEl.innerText = "Geolocation unsupported. Defaulting to Universitas Brawijaya.";
        return;
    }

    navigator.geolocation.getCurrentPosition(
        position => {
            currentLat = position.coords.latitude;
            currentLon = position.coords.longitude;
            locationMessage = "Using your current GPS location.";
            locEl.innerText = locationMessage;
        },
        error => {
            console.log("Location error:", error);
            locationMessage = "Location access denied. Defaulting to Universitas Brawijaya.";
            locEl.innerText = locationMessage;
        }
    );
}

// =========================
// CHART UTILS
// =========================
function getAdaptiveRange(values, padding = 5) {
    if (!values || values.length === 0) return { min: 0, max: 100 };
    const min = Math.min(...values);
    const max = Math.max(...values);
    return {
        min: Math.floor(min - padding),
        max: Math.ceil(max + padding)
    };
}

function createChart(elementId, label, borderColor, backgroundColor) {
    const ctx = document.getElementById(elementId);
    if (!ctx) return null;

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: label,
                data: [],
                tension: 0.4,
                borderColor: borderColor,
                backgroundColor: backgroundColor,
                fill: 'start',
                pointRadius: 4,
                pointBackgroundColor: borderColor,
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { family: 'Inter', size: 11 } }
                },
                y: {
                    beginAtZero: false,
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    ticks: { font: { family: 'Inter', size: 11 } }
                }
            }
        }
    });
}

function initCharts() {
    tempChart = createChart('tempChart', 'Temperature (°C)', '#3b82f6', 'rgba(59, 130, 246, 0.1)');
    humChart = createChart('humChart', 'Humidity (%)', '#10b981', 'rgba(16, 185, 129, 0.1)');
    luxChart = createChart('luxChart', 'Lux (lx)', '#f59e0b', 'rgba(245, 158, 11, 0.1)');
}

// =========================
// API ACTIONS
// =========================
function exportDatabase() {
    window.location.href = '/api/export/xlsx';
}

async function clearDatabase() {
    const confirmClear = confirm("Are you sure you want to clear all sensor data?");
    if (!confirmClear) return;

    try {
        const response = await fetch('/api/clear', { method: 'POST' });
        const result = await response.json();
        alert(result.message);
        updateDashboard();
    } catch (e) {
        console.error("Clear DB error:", e);
    }
}

// =========================
// DATA FORMATTERS
// =========================
function getEnvironmentDescription(status) {
    const maps = {
        "OPTIMAL FOR TOMATO": "Environmental conditions are ideal for tomato cultivation.",
        "FUNGAL RISK": "High humidity and temperature increase fungal disease risk.",
        "HEAT STRESS": "Extreme heat may damage tomato growth and fruit development.",
        "WATER STRESS": "Humidity is too low and may increase water stress."
    };
    return maps[status] || "Conditions are acceptable but not fully optimal.";
}

function getLightDescription(status) {
    const maps = {
        "VERY LOW LIGHT": "Light intensity is critically low for tomato growth.",
        "LOW LIGHT": "Cloudy or shaded condition detected.",
        "MODERATE LIGHT": "Moderate lighting condition detected.",
        "GOOD SUNLIGHT": "Lighting is suitable for photosynthesis."
    };
    return maps[status] || "Very intense sunlight detected.";
}

// =========================
// UPDATE DASHBOARD
// =========================
async function updateDashboard() {
    try {
        const [dataRes, weatherRes] = await Promise.all([
            fetch('/api/latest'),
            fetch(`/api/weather?lat=${currentLat}&lon=${currentLon}`)
        ]);

        const data = await dataRes.json();
        const weather = await weatherRes.json();

        if (!data || data.length === 0) return;

        const latest = data[data.length - 1];

        // Update Status Cards
        document.getElementById("envStatus").innerText = latest.environment_status;
        document.getElementById("lightStatus").innerText = latest.light_status;
        document.getElementById("fanStatus").innerText = latest.fan_status;
        document.getElementById("pumpStatus").innerText = latest.pump_status;
        document.getElementById("weatherStatus").innerText = weather.weather;

        // Update Descriptions
        document.getElementById("envDesc").innerText = getEnvironmentDescription(latest.environment_status);
        document.getElementById("lightDesc").innerText = getLightDescription(latest.light_status);
        document.getElementById("fanDesc").innerText = latest.fan_status === "ON"
            ? "Cooling system is actively reducing greenhouse temperature."
            : "Cooling system is inactive.";
        document.getElementById("pumpDesc").innerText = latest.pump_status === "ON"
            ? "Irrigation system is supplying water."
            : "Irrigation system is inactive.";
        document.getElementById("weatherDesc").innerText = `Outside: ${weather.temperature}°C | Humidity: ${weather.humidity}%`;

        // Update Table
        updateTable(data);

        // Update Charts
        updateCharts(data);

    } catch (error) {
        console.error("Dashboard update error:", error);
    }
}

function updateTable(data) {
    const tableBody = document.getElementById("tableBody");
    if (!tableBody) return;

    tableBody.innerHTML = [...data].reverse().map(row => `
        <tr>
            <td>${row.id}</td>
            <td>${row.timestamp}</td>
            <td>${row.temperature}</td>
            <td>${row.humidity}</td>
            <td>${row.lux}</td>
        </tr>
    `).join('');
}

function updateCharts(fullData) {
    // Keep charts readable by showing only the last 30 points
    const data = fullData.slice(-30);
    const labels = data.map(row => row.timestamp.split(" ")[1]);

    // Temp Chart
    const tempValues = data.map(row => row.temperature);
    const tempRange = getAdaptiveRange(tempValues, 2);
    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = tempValues;
    tempChart.options.scales.y.min = tempRange.min;
    tempChart.options.scales.y.max = tempRange.max;
    tempChart.update();

    // Hum Chart
    const humValues = data.map(row => row.humidity);
    const humRange = getAdaptiveRange(humValues, 5);
    humChart.data.labels = labels;
    humChart.data.datasets[0].data = humValues;
    humChart.options.scales.y.min = 0;
    humChart.options.scales.y.max = humRange.max;
    humChart.update();

    // Lux Chart
    const luxValues = data.map(row => row.lux);
    const luxRange = getAdaptiveRange(luxValues, 10);
    luxChart.data.labels = labels;
    luxChart.data.datasets[0].data = luxValues;
    luxChart.options.scales.y.min = 0;
    luxChart.options.scales.y.max = luxRange.max;
    luxChart.update();
}

function updateLiveClock() {
    const clockEl = document.getElementById("liveTime");
    if (clockEl) {
        const now = new Date();
        clockEl.innerText = now.toLocaleTimeString();
    }
}
