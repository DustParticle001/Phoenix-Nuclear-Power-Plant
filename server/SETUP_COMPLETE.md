# PWR Backend - Complete Setup Summary

## ✅ Project Structure Ready

All simulation engines and infrastructure are set up with **zero implementation** - just boilerplate and structure.

---

## 📦 Libraries Integrated

### Numerical Computing
- **Apache Commons Math 3.6.1**
  - `FirstOrderIntegrator` (Dormand-Prince RK45)
  - ODE solvers for neutronics, T-H equations
  - Linear algebra utilities

- **ND4J 1.0.0-M1.1**
  - N-dimensional arrays (matrices)
  - GPU-ready computation (fallback to CPU)
  - Used for large matrix operations in T-H code

- **Deeplearning4j 1.0.0-M1.1**
  - Optional: Neural networks for ML-based control strategies
  - Not required for core simulation

### Data Persistence
- **PostgreSQL 42.7.1** (production)
- **H2 Database** (dev/test)
- **Spring Data JPA** - ORM for state snapshots

### Configuration & Serialization
- **Jackson DataFormat YAML**
  - Config parsing for reactor parameters
  - YAML support in application.yml

### Testing
- **JUnit 5**
- **AssertJ** - fluent assertions for numerical tests

### Communication
- **Spring Boot WebSocket** (ready for real-time updates)
- **Spring Boot Web** (REST API)
- **Spring Boot Data JPA** (database integration)

---

## 🏗️ Architecture

```
pwr-backend/
├── src/main/java/com/pwrsim/backend/
│   ├── controller/
│   │   └── ReactorController.java          ← REST API endpoints
│   │
│   ├── model/
│   │   └── ReactorState.java               ← JPA entity for persistence
│   │
│   ├── repository/
│   │   └── ReactorStateRepository.java     ← Data access layer
│   │
│   ├── simulation/                         ← ⭐ CORE PHYSICS ENGINES
│   │   ├── NeutronicsEngine.java           (point kinetics model)
│   │   ├── ThermalHydraulicsEngine.java    (lumped 1-D model)
│   │   ├── ControlSystemEngine.java        (PID control + safety)
│   │   ├── ReactorSimulationService.java   (orchestrator)
│   │   └── FMICoupling.java                (external code coupling)
│   │
│   └── PwrSimulationApplication.java       ← Spring Boot main
│
├── src/main/resources/
│   └── application.yml                     ← Complete config structure
│
└── pom.xml                                 ← All libraries ready
```

---

## 🔧 What's Ready to Use

### 1. **NeutronicsEngine**
- `DormandPrince54Integrator` for ODE solving
- Point kinetics model structure
- Placeholder methods for:
  - `computeReactivity(T, B, CRpos, ρ_mod, Xe)` 
  - `step(state, Δt, ρ)`
  - Xenon transient feedback
- State: power, reactivity, precursor concentration, xenon

### 2. **ThermalHydraulicsEngine**
- ND4J matrix operations ready
- Dormand-Prince integrator
- Placeholder methods for:
  - Core outlet temperature calculation
  - Pressurizer pressure/level control
  - Primary loop pressure drop
  - Coolant property calculations
- State: T_in, T_out, T_avg, P, L_pz, flow rates

### 3. **ControlSystemEngine**
- Control modes: MANUAL, AUTO, STARTUP, POWER_OPS, SHUTDOWN, SCRAM, ECCS
- Placeholder PID implementations for:
  - Control rod positioning
  - Pressurizer heater/spray
  - Power/temperature control
  - Scram logic + ECCS actuation
- Operator command processor

### 4. **ReactorSimulationService** (Orchestrator)
- Initialization from reactor parameters
- Simulation stepping (coordinates all engines)
- State persistence to database
- Operator commands interface

### 5. **FMICoupling**
- Ready for external model integration
- Placeholder for SAM, Modelica, OpenMC coupling
- FMI standard interface structure

---

## 🗄️ Database Setup

`ReactorState` JPA entity with fields for:
- Timestamp
- Neutronics: power, reactivity, boron concentration, control rod position
- T-H: core temps (in/out/avg), pressures, flows, pressurizer state
- System: operating mode, scram/ECCS flags, alarms

**Repository** ready with queries:
- Get latest state
- Query by time window
- Find scram events

---

## 📝 REST API Endpoints (Ready)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/reactor/status` | Quick status (power, T, P) |
| GET | `/api/reactor/status/detailed` | Full state snapshot |
| POST | `/api/reactor/control` | Send commands (power, temp, boron, CR pos) |
| POST | `/api/reactor/simulate/step` | Single timestep |
| POST | `/api/reactor/simulate/start` | Start simulation |
| POST | `/api/reactor/simulate/stop` | Stop simulation |

---

## ⚙️ Configuration (application.yml)

Complete configuration structure for:
- Simulation timestepping (ODE integrator tolerances)
- FMI coupling (path to external .fmu files)
- Safety limits & setpoints
- Database history parameters
- GPU acceleration options (ND4J)

---

## 🎯 Next Steps: Implementation

Once you provide **US-EPR reactor documentation**, implement:

### 1. **Extract Design Parameters**
From FSAR / Technical Specs extract:
- Core power, geometry, heat transfer
- Primary/secondary loop flow, temps
- Pressurizer design (volume, heater/spray capability)
- Control rod worth curves
- Reactivity feedback coefficients (Doppler, moderator density, Xe, boron)
- Safety setpoints (scram, ECCS, limits)

### 2. **Implement Neutronics Model**
In `NeutronicsEngine.step()`:
```java
// Point kinetics equations:
// dn/dt = (ρ - β) / Λ * n + λ * C
// dC/dt = β / Λ * n - λ * C

// Use integrator.integrate() with FirstOrderDifferentialEquations
```

### 3. **Implement Thermal-Hydraulics**
In `ThermalHydraulicsEngine.step()`:
```java
// Energy balance: Q = m_dot * cp * ΔT
// Momentum balance: dP/dt from friction + gravity
// Pressurizer P-V-T equations
// SG heat transfer: U*A*(T_primary - T_secondary)
```

### 4. **Implement Control Logic**
In `ControlSystemEngine`:
```java
// PID: error = setpoint - measured
// output = Kp*error + Ki*integral(error) + Kd*derivative(error)
// Saturation + ramp rate limiting
```

### 5. **Implement Feedback Coupling**
In `ReactorSimulationService.step()`:
```java
// 1. Compute reactivity from T feedback
// 2. Step neutronics → get new power
// 3. Step T-H with new power → get new temperatures
// 4. Check safety limits → trigger scram/ECCS if needed
```

---

## 📊 Expected Performance

- **Point kinetics + lumped T-H**: ~10-50 ms per timestep (real-time capable)
- **With FMI coupling to SAM**: ~500-2000 ms per timestep (slower but more accurate)
- **Full CFD (OpenFOAM)**: Too slow for real-time (~hours for transient)

---

## 🚀 Build & Run

```bash
mvn clean package

java -jar target/pwr-backend-1.0.0.jar
```

Server runs on `http://localhost:8080`

---

## 📖 Documentation Files

- `pom.xml` - All dependencies
- `application.yml` - Configuration structure
- `SERVER_API.md` - API reference
- Code comments - Javadoc for every engine

---

## ✏️ TODO Markers

Search for `// TODO:` in simulation engines - all logic placeholders clearly marked.

**Total setup**: ~2500 LOC framework, zero implementation logic = ready for your physics code.
