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
│   │   ├── Annunciators/         # rack definitions, windows, flash groups
│   │   ├── Editor/               # gauge face baker, annunciator rack builder
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
indicator lamp states, gauge values and annunciator windows. Everything is keyed
by definition UID, so no scene wiring is involved. Server side it's
`data/io_definitions.json` + `io_state.py`. See
`client/unbuilt/docs/server-io-sync.md` and `server-python/API.md`.

`rcp_sim.py` is the biggest consumer: the four reactor coolant pumps with their
electrical supply (NBUS feeders, SBO-backed auxiliary MCCs with automatic
transfer), motor run-up and flywheel coastdown, ammeter and loop flow gauges,
and the protection that trips them. `rod_sim.py` is the newest and the most
temporary: the Westinghouse rod control system (eight banks, the overlap
sequence, the rod stops) driven by the switches on the MRCS section, with a
deliberately minimal reactivity-and-period power model hung off it — plus the
boric acid control and the two RPS trip breakers, which are camping there until
CVCS and RPS get files of their own. `rcs_thermal.py` turns that power and the
pumps' flow into the primary temperatures: the programmed Tavg, the core dT and
each loop's hot and cold leg. `commands.py` is the instructor's console that
inserts the casualties — `/turnswitch`, `/fault`, `/component`, `/rods`,
`/rcs`, typed into the server terminal. `--no-sim` disables the lot. See
`server/API.md`.

### Annunciator racks
A rack is described rather than modelled: an `AnnunciatorRackDefinition` holds the
size, the window grid, the legends and the lens colours (both imported from CSV),
and `Editor/AnnunciatorRackBuilder.cs` generates the frame mesh, the lens mesh,
the HDRP materials, the legends and a prefab from it. Windows are outputs the
**client** defines — their uids come from the definition and register themselves
with the server on the first sync — and racks sharing a flash group blink as one
panel, across as many racks as are in the group. See the annunciator sections of
`docs/interactable-api-usage-guide.md` and `docs/server-io-sync.md`.

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
