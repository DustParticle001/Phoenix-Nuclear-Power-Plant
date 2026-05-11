# Phoenix-Nuclear-Power-Plant
A PWR nuclear reactor game based on the US-EPR type. 2 people developing currently.

## Description
Version: Pre-alpha v0.0.2
A passion project of <a href="https://github.com/DustParticle001">DustParticle</a> and <a href="https://github.com/nektarii">nektarii</a>.
Based on the US-EPR reactor type.
Doesn't have any actual reactors built so not guaranteed to be accurate.
If someone is interested please contact <a href="https://discordapp.com/users/899249692540563516">me</a>. (Any help is appreciated)
The discord server is being built but the link will be <a href="https://google.com">here</a> once it's done.

-----

## Unity
### Unity Project Structure
```
client/
├── Assets/
│   └── ...                       # Way too much stuff
├── Packages/
│   ├── manifest.json
│   └── packages-lock.json
├── ProjectSettings/
│   └── ...                       # Way too much stuff
└── .vsconfig
```

### Version
6000.4.5f1+                       # I'm not sure about this working on other versions

### Todo Client
- Add control room
- Server player location          # For multiplayer
- Interactive switches
- Models
- Fetching server?                # I don't know how this will work

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
