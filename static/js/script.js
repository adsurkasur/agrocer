// =========================
// STATE
// =========================
let currentLat = -7.956;
let currentLon = 112.6159;
let locationMessage = "Using your current GPS location.";

// CHARTS INSTANCES
let tempChart, humChart, luxChart;

// THRESHOLDS STATE
let thresholds = {
    fan_on_temp: 30.0,
    fan_off_temp: 28.0,
    pump_on_humidity: 40.0,
    pump_off_humidity: 45.0
};

// =========================
// UTILS & VALIDATION
// =========================
function isValidNumber(v) {
    return typeof v === 'number' && !isNaN(v) && isFinite(v);
}

function sanitizeValue(v, fallback) {
    const n = parseFloat(v);
    return isValidNumber(n) ? n : fallback;
}

// =========================
// INITIALIZATION
// =========================
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    getLocation();
    updateDashboard();
    fetchThresholds();

    // Refresh intervals
    setInterval(updateDashboard, 1000); 
    setInterval(updateLiveClock, 1000);
    setInterval(fetchThresholds, 5000); // Increased slightly from 1s to be reasonable
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

function createChart(elementId, label, borderColor, backgroundColor, extraDatasets = []) {
    const ctx = document.getElementById(elementId);
    if (!ctx) return null;

    const datasets = [{
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
        pointHoverRadius: 6,
        z: 10
    }, ...extraDatasets];

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 }, // Optimization for realtime
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        font: { family: 'Inter', size: 10 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const ds = context.dataset;
                            if (ds.isEvent) {
                                return `[EVENT] ${ds.actuator}: ${context.raw.prev} -> ${context.raw.new}`;
                            }
                            return `${ds.label}: ${context.parsed.y}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { family: 'Inter', size: 11 } }
                },
                y: {
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    ticks: { font: { family: 'Inter', size: 11 } }
                }
            }
        }
    });
}

function initCharts() {
    // Threshold and Event Datasets definitions
    const thresholdStyle = (label, color) => ({
        label: label,
        data: [],
        borderColor: color,
        borderWidth: 2,
        borderDash: [5, 5],
        fill: false,
        pointRadius: 0,
        z: 5
    });

    const eventStyle = (actuator, color) => ({
        label: `${actuator} Events`,
        data: [],
        borderColor: color,
        backgroundColor: color,
        pointStyle: 'rectRot',
        pointRadius: 10,
        pointHoverRadius: 12,
        showLine: false,
        isEvent: true,
        actuator: actuator,
        z: 20
    });

    tempChart = createChart('tempChart', 'Temperature (°C)', '#3b82f6', 'rgba(59, 130, 246, 0.1)', [
        thresholdStyle('FAN ON', '#ef4444'),
        thresholdStyle('FAN OFF', '#f87171'),
        eventStyle('Fan', '#1e293b')
    ]);

    humChart = createChart('humChart', 'Humidity (%)', '#10b981', 'rgba(16, 185, 129, 0.1)', [
        thresholdStyle('PUMP ON', '#ef4444'),
        thresholdStyle('PUMP OFF', '#f87171'),
        eventStyle('Pump', '#1e293b')
    ]);

    luxChart = createChart('luxChart', 'Lux (lx)', '#f59e0b', 'rgba(245, 158, 11, 0.1)');
}

// =========================
// API ACTIONS
// =========================
function exportDatabase() {
    window.location.href = '/api/export/xlsx';
}

async function fetchThresholds() {
    try {
        const res = await fetch('/api/thresholds');
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();
        
        // Defensive merge: only accept valid numbers
        if (data) {
            thresholds.fan_on_temp = sanitizeValue(data.fan_on_temp, thresholds.fan_on_temp);
            thresholds.fan_off_temp = sanitizeValue(data.fan_off_temp, thresholds.fan_off_temp);
            thresholds.pump_on_humidity = sanitizeValue(data.pump_on_humidity, thresholds.pump_on_humidity);
            thresholds.pump_off_humidity = sanitizeValue(data.pump_off_humidity, thresholds.pump_off_humidity);
        }
    } catch (e) {
        console.warn("Threshold fetch failed, using fallbacks:", e);
    }
}

async function fetchActuatorLogs() {
    try {
        const res = await fetch('/api/actuator-logs?limit=10');
        const logs = await res.json();
        updateLogTable(logs);
        updateActuatorStats(logs);
    } catch (e) {
        console.error("Failed to fetch actuator logs:", e);
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
        document.getElementById("fanStatus").innerText = latest.fan_status === 1 ? "ON" : "OFF";
        document.getElementById("pumpStatus").innerText = latest.pump_status === 1 ? "ON" : "OFF";
        document.getElementById("weatherStatus").innerText = weather.weather;

        // Update Descriptions
        document.getElementById("envDesc").innerText = getEnvironmentDescription(latest.environment_status);
        document.getElementById("lightDesc").innerText = getLightDescription(latest.light_status);
        document.getElementById("fanDesc").innerText = latest.fan_status === 1
            ? "Cooling system is actively reducing greenhouse temperature."
            : "Cooling system is inactive.";
        document.getElementById("pumpDesc").innerText = latest.pump_status === 1
            ? "Irrigation system is supplying water."
            : "Irrigation system is inactive.";

        // Update Table
        updateTable(data);

        // Update Charts
        updateCharts(data);

        // Update Logs & Stats
        fetchActuatorLogs();

    } catch (error) {
        console.error("Dashboard update error:", error);
    }
}

function updateTable(data) {
    const tableBody = document.getElementById("tableBody");
    if (!tableBody) return;

    tableBody.innerHTML = [...data].reverse().slice(0, 10).map(row => `
        <tr>
            <td>${row.id}</td>
            <td>${row.timestamp.split(" ")[1]}</td>
            <td>${row.temperature}°C</td>
            <td>${row.humidity}%</td>
            <td>${row.lux} lx</td>
        </tr>
    `).join('');
}

function updateLogTable(logs) {
    const logBody = document.getElementById("logTableBody");
    if (!logBody) return;

    if (!logs || logs.length === 0) {
        logBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--text-muted);">No activation events yet</td></tr>';
        return;
    }

    logBody.innerHTML = logs.map(log => `
        <tr>
            <td>${log.timestamp ? log.timestamp.split(" ")[1] : '---'}</td>
            <td><span class="badge actuator-${String(log.actuator_name).toLowerCase()}">${log.actuator_name}</span></td>
            <td>${log.previous_state == 1 ? 'ON' : 'OFF'} <i class="fas fa-arrow-right"></i> ${log.new_state == 1 ? 'ON' : 'OFF'}</td>
            <td>${log.trigger_value} (${log.trigger_type})</td>
        </tr>
    `).join('');
}

function updateActuatorStats(logs) {
    const fanCount = logs.filter(l => l.actuator_name === "Fan" && l.new_state === 1).length;
    const pumpCount = logs.filter(l => l.actuator_name === "Pump" && l.new_state === 1).length;
    
    // Note: This is an approximation based on the limit. 
    // In a real app, you'd fetch totals from a summary endpoint.
    document.getElementById("totalFan").innerText = fanCount;
    document.getElementById("totalPump").innerText = pumpCount;
    if (logs.length > 0) {
        document.getElementById("latestEventTime").innerText = logs[0].timestamp.split(" ")[1];
    }
}

function updateCharts(fullData) {
    const data = fullData.slice(-30);
    const labels = data.map(row => row.timestamp.split(" ")[1]);

    // Temp Chart
    const tempValues = data.map(row => sanitizeValue(row.temperature, 0));
    const tempRange = getAdaptiveRange(tempValues, 5);
    
    // Diagnostic
    console.log(`[DIAG] Temp: points=${tempValues.length}, range=[${tempRange.min}, ${tempRange.max}], thresholds=[${thresholds.fan_on_temp}, ${thresholds.fan_off_temp}]`);

    // Detect Fan Events in current window
    const fanEvents = [];
    for (let i = 1; i < data.length; i++) {
        if (data[i].fan_status !== data[i-1].fan_status) {
            fanEvents.push({
                x: data[i].timestamp.split(" ")[1],
                y: sanitizeValue(data[i].temperature, 0),
                prev: data[i-1].fan_status == 1 ? 'ON' : 'OFF',
                new: data[i].fan_status == 1 ? 'ON' : 'OFF'
            });
        }
    }

    tempChart.data.labels = labels;
    tempChart.data.datasets[0].data = tempValues;
    tempChart.data.datasets[1].data = new Array(labels.length).fill(thresholds.fan_on_temp);
    tempChart.data.datasets[2].data = new Array(labels.length).fill(thresholds.fan_off_temp);
    tempChart.data.datasets[3].data = fanEvents;
    
    // Defensive Y-Axis
    const tMin = Math.min(tempRange.min, thresholds.fan_off_temp - 2);
    const tMax = Math.max(tempRange.max, thresholds.fan_on_temp + 2);
    tempChart.options.scales.y.min = isValidNumber(tMin) ? tMin : 0;
    tempChart.options.scales.y.max = isValidNumber(tMax) ? tMax : 50;
    tempChart.update('none'); 

    // Hum Chart
    const humValues = data.map(row => sanitizeValue(row.humidity, 0));
    const humRange = getAdaptiveRange(humValues, 10);
    
    // Detect Pump Events
    const pumpEvents = [];
    for (let i = 1; i < data.length; i++) {
        if (data[i].pump_status !== data[i-1].pump_status) {
            pumpEvents.push({
                x: data[i].timestamp.split(" ")[1],
                y: sanitizeValue(data[i].humidity, 0),
                prev: data[i-1].pump_status == 1 ? 'ON' : 'OFF',
                new: data[i].pump_status == 1 ? 'ON' : 'OFF'
            });
        }
    }

    humChart.data.labels = labels;
    humChart.data.datasets[0].data = humValues;
    humChart.data.datasets[1].data = new Array(labels.length).fill(thresholds.pump_on_humidity);
    humChart.data.datasets[2].data = new Array(labels.length).fill(thresholds.pump_off_humidity);
    humChart.data.datasets[3].data = pumpEvents;
    
    // Defensive Y-Axis
    const hMin = Math.min(0, thresholds.pump_on_humidity - 10);
    const hMax = Math.max(humRange.max, thresholds.pump_off_humidity + 10);
    humChart.options.scales.y.min = isValidNumber(hMin) ? hMin : 0;
    humChart.options.scales.y.max = isValidNumber(hMax) ? hMax : 100;
    humChart.update('none');

    // Lux Chart
    const luxValues = data.map(row => row.lux);
    const luxRange = getAdaptiveRange(luxValues, 50);
    luxChart.data.labels = labels;
    luxChart.data.datasets[0].data = luxValues;
    luxChart.options.scales.y.max = luxRange.max;
    luxChart.update('none');
}

function updateLiveClock() {
    const clockEl = document.getElementById("liveTime");
    if (clockEl) {
        const now = new Date();
        clockEl.innerText = now.toLocaleTimeString();
    }
}
