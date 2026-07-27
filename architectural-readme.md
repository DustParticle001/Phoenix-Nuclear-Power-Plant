-----

## Unity
### Unity Project Structure
```
client/unbuilt/
├── Assets/
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

### Todo Client
- Add control room
- Server player location        
- Interactive switches
- Models
- Fetching server?               

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
