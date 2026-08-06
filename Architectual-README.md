# Architectual README
Information about the client and backend.

## Unity
### Unity Project Structure
```
client/unbuilt/
├── Assets/
│   ├── Scenes/
│   │   ├── HomeScene.unity       # entry scene - join a server
│   │   └── MainScene.unity       # control room
│   ├── Scripts/
│   │   ├── Networking/           # ServerConnection, ControlRoomTemplate
│   │   ├── UI/                   # HomeScreen
│   │   └── ...
│   └── ...
├── Packages/
│   ├── manifest.json
│   └── packages-lock.json
├── ProjectSettings/
│   └── ...                      
└── .vsconfig
```

### Version
6000.4.5f1+                   

### Entry flow
Build order is `HomeScene` (0) then `MainScene` (1) - both must stay in Build
Settings. There is no offline mode: `HomeScene` asks for a server address, joins
it (`/api/info` + `/api/template`), and only then loads the control room, so the
scene always has server data behind it. `ServerConnection.Instance` carries the
connection across the scene change. See `client/unbuilt/docs/joining-a-server.md`.

### Live I/O
`IoSync` (on the same persistent object) exchanges state with the server twice a
second: up go all switch positions, down come switches other players moved,
indicator lamp states and gauge values. Everything is keyed by definition UID, so
no scene wiring is involved. Server side it's `data/io_definitions.json` +
`io_state.py`. See `client/unbuilt/docs/server-io-sync.md` and
`server-python/API.md`.

`rcp_sim.py` is the first consumer: a test simulation that runs the four RCP
frequency gauges up/down off their power switches (`--no-sim` to disable).

### Todo Client
- Add control room
- Server player location        
- Interactive switches
- Models
- Bind template data (panels, annunciator legends) to the scene

-----

## PWR Simulation Backend
Java Spring Boot backend for Unity PWR (Pressurized Water Reactor) simulation game.

### Project Structure
```
pwr-backend/
├── src/
│   ├── main/
│   │   ├── java/com/pwrsim/backend/
│   │   │   ├── controller/       # REST API endpoints
│   │   │   ├── service/          # Business logic
│   │   │   ├── entity/           # JPA entities
│   │   │   ├── repository/       # Data access
│   │   │   └── PwrSimulationApplication.java
│   │   └── resources/
│   │       └── application.yml   # Configuration
│   └── test/
└── pom.xml                       # Maven configuration
```

### Prerequisites
- Java 17+
- Maven 3.6+

### Build & Run
```bash
# Build project
mvn clean package

# Run application
mvn spring-boot:run

# Or run JAR directly
java -jar target/pwr-backend-1.0.0.jar
```

Server runs on `http://localhost:8080`

### API Endpoints
#### Reactor Status
- **GET** `/api/reactor/status` - Get current reactor status

#### Reactor Control
- **POST** `/api/reactor/control` - Send control commands

### Features
- ✅ Spring Boot 3.2
- ✅ REST API for game communication
- ✅ WebSocket support (ready for real-time updates)
- ✅ JPA/Hibernate for persistence
- ✅ H2 database (dev) / PostgreSQL (prod)
- ✅ CORS enabled for Unity integration

### Next Steps
1. Implement entity models for Reactor, Core, Pump, etc.
2. Add service layer for simulation logic
3. Expand API endpoints for game requirements
4. Add WebSocket handlers for real-time updates
5. Configure environment-specific profiles

### Development Tips
- H2 Console: `http://localhost:8080/h2-console`
- Check logs in `src/main/resources/application.yml`
- Modify CORS origins as needed for Unity game server

-----

##### Copyright:
<a href="https://github.com/DustParticle001/Phoenix-Nuclear-Power-Plant">Phoenix Nuclear Power Plant</a> © 2026 by <a href="https://github.com/DustParticle001">DustParticle</a> is licensed under <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/">CC BY-NC-ND 4.0</a>
