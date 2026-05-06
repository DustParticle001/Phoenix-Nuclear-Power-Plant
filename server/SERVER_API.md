# PWR Backend Server API

## Base URL
```
http://localhost:8080/api
```

## Endpoints

### Reactor Status

**GET** `/reactor/status`

Get current reactor state and metrics.

**Response (200 OK)**
```json
{
  "state": "Online",
  "temperature": 320.0,
  "pressure": 15.5,
  "powerLevel": 100.0
}
```

| Field | Type | Description |
|-------|------|-------------|
| state | string | Reactor state (Online, Offline, Critical, etc.) |
| temperature | double | Core temperature (°C) |
| pressure | double | System pressure (MPa) |
| powerLevel | double | Reactor power output (%) |

---

### Reactor Control

**POST** `/reactor/control`

Send control command to reactor.

**Request Body**
```json
{
  "action": "start",
  "value": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| action | string | ✓ | Control action (start, stop, scram, adjust_rods, etc.) |
| value | double | ✗ | Optional numeric parameter for the action |

**Response (200 OK)**
```json
"Command received: start"
```

---

## Example Requests

### cURL

Get status:
```bash
curl http://localhost:8080/api/reactor/status
```

Send control command:
```bash
curl -X POST http://localhost:8080/api/reactor/control \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

### JavaScript/Fetch

Get status:
```javascript
fetch('http://localhost:8080/api/reactor/status')
  .then(r => r.json())
  .then(data => console.log(data));
```

Send command:
```javascript
fetch('http://localhost:8080/api/reactor/control', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ action: 'stop' })
})
  .then(r => r.text())
  .then(msg => console.log(msg));
```

---

## CORS

All endpoints allow CORS from any origin (`*`).

---

## Planned Features

- ✗ WebSocket real-time updates
- ✗ Detailed system metrics (pump status, coolant flow, etc.)
- ✗ Historical data / logging
- ✗ Advanced control sequences
- ✗ Authentication / Authorization
