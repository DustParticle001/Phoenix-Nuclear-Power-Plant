# PWR Backend - Required Libraries & Frameworks for Realistic Simulation

## Overview
Implementing a realistic PWR (Pressurized Water Reactor) simulation requires coupling multiple physics domains: **neutronics**, **thermal-hydraulics**, **core mechanics**, and **control systems**.

---

## 1. Core Physics & Neutronics

### Primary Options
- **OpenMC** (Python-based, but can be called from Java)
  - Monte Carlo neutron transport
  - Open-source, widely used in academic/research settings
  - Coupling available with thermal-hydraulics codes
  - Repository: https://github.com/openmc-dev/openmc

- **SHIFT** (ORNL - Exascale Computing Project)
  - Parallel Monte Carlo for large-scale reactor analysis
  - More computationally efficient than OpenMC for full-core analysis

- **ARMI** (Advanced Reactor Modeling Interface - TerraPower)
  - Framework for coupling multiple physics codes
  - Python-based, hub-and-spoke architecture for physics kernels
  - Repository: https://github.com/terrapower/armi

### Point Kinetics (Simplified Neutronics)
For real-time game simulation, a **point kinetics model** is more practical:
- Differential equations for reactor power vs. reactivity, delayed neutrons
- Libraries: Apache Commons Math (ODE solvers)
- Much faster than Monte Carlo, suitable for interactive gameplay

---

## 2. Thermal-Hydraulics

### System-Level (1-D/Lumped)
These model heat transfer, coolant flow, pressure drops without CFD complexity:

- **RELAP5** (NRC - proprietary, but legacy versions open-source)
  - Industry standard for PWR transient analysis
  - Validates against real reactor data
  - Coupling frameworks available

- **TRACE** (NRC successor to RELAP5)
  - More modern, validated for PWR accidents
  - Proprietary but research access available

- **SAM (System Analysis Module)** (ANL)
  - Open-source system-level code
  - Fast transient analysis, real-time capable
  - Repository: https://github.com/idaholab/sam

- **Modelica/ThermoPower**
  - Open-source Modelica libraries for power plant simulation
  - Component-based (reactor, steam generator, pump, etc.)
  - Declarative equations, easy to modify
  - Repository: https://github.com/casella/ThermoPower

### CFD (Detailed 3-D, Expensive)
- **OpenFOAM** (+ Cardinal coupling to OpenMC)
  - Open-source CFD framework
  - Can simulate detailed subchannel flow/temperature
  - Slow (not real-time), expensive computationally

---

## 3. Java Numerical Libraries

For ODE solvers, matrix operations, and numerical calculations:

### Apache Commons Math 3.x
```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-math3</artifactId>
    <version>3.6.1</version>
</dependency>
```
- ODE solvers: RK45, Adams-Bashforth, etc.
- Linear algebra, statistics
- **Good for**: Point kinetics, simple T-H models

### ND4J (N-Dimensional Arrays for Java)
```xml
<dependency>
    <groupId>org.nd4j</groupId>
    <artifactId>nd4j-native-platform</artifactId>
    <version>1.0.0-M1.1</version>
</dependency>
```
- Fast matrix operations (CPU/GPU)
- Neural networks (if using ML for control)
- Better performance for complex calculations

### JScience / JScilab
- Scientific computing for Java
- Less maintained, but still available

---

## 4. Coupling & Co-Simulation

### BCVTB (Building Controls Virtual Test Bed)
- Java-based co-simulation environment
- Can couple Fortran/C codes, Modelica, and custom Java
- Developed at Lawrence Berkeley National Lab
- Good for: Linking multiple physics codes

### FMI (Functional Mockup Interface)
- Standard for model exchange between tools
- Many tools support FMI (Modelica, Simulink, etc.)
- **FMI4j** - Java library for FMI
```xml
<dependency>
    <groupId>no.ntnu.idi.fmi4j</groupId>
    <artifactId>fmi4j</artifactId>
    <version>0.48</version>
</dependency>
```

---

## 5. Control Systems

### Control Theory Libraries
- **Controlics** (not actively maintained)
- **Java Control Library** (custom implementations needed)
- **Apache Commons** Math + custom control algorithms

### Reactor Control Logic
- Point kinetics equations with **reactivity feedback**
- **Feedback**: Temperature reactivity coefficient, power coefficient
- **Control rods**: Worth curves, dropping speed
- **Coolant pumps**: Flow rate modulation
- **Safety systems**: Scram logic, emergency cooling

---

## 6. Data Persistence & State Management

### Database
```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.6.0</version>
</dependency>
```
- PostgreSQL for historical data, logging
- H2 in-memory for dev/testing (already in your pom.xml)

### Time-Series Database (Optional)
- **InfluxDB** - for sensor data, transient logging
- **TimescaleDB** (PostgreSQL extension)

---

## 7. Real-Time & WebSocket Communication

### Already in your pom.xml
- Spring Boot WebSocket support ✓
- Spring Data JPA ✓

### Additional (Optional)
- **Project Reactor** - reactive streams for non-blocking async
- **RxJava** - similar reactive approach

---

## Recommended Implementation Strategy

### Phase 1: Core Simulation (MVP)
Use **point kinetics + lumped thermal-hydraulics**:
- Apache Commons Math for ODE solving
- Custom Java classes for reactor state
- SQLite/H2 for state persistence
- ~1000 lines of simulation code
- **Real-time capable**: <50ms per time step

### Phase 2: Enhanced Physics
Integrate **SAM or Modelica (ThermoPower)**:
- More detailed subchannel/system modeling
- Safety system simulation
- Multi-loop primary circuit
- Pressurizer heater/spray control

### Phase 3: Full Coupling
Link **OpenMC (neutronics) + SAM (T-H)**:
- Feedback between neutronics and thermal-hydraulics
- **Expensive**: ~1-2s per time step (not real-time)
- More suitable for offline analysis

---

## Required Input from US-EPR Docs

Once you provide your reactor documentation, extract:

1. **Core Design**
   - Number of fuel assemblies, power density
   - Burn-up characteristics, reactivity curve

2. **Thermal-Hydraulic Design**
   - Primary loop flow rate, T_in, T_out
   - Secondary loop (steam generator) design
   - Pressurizer setup (heater, spray, vent valves)
   - Safety/emergency cooling specs

3. **Reactor Physics**
   - Temperature reactivity coefficients (Doppler, moderation)
   - Neutron lifetime, delayed neutron fractions
   - Control rod worth curves
   - Xenon/Samarium poisoning

4. **Control Systems**
   - Power setpoint control logic
   - Pressurizer pressure control
   - Charging/letdown balance
   - Scram setpoints

5. **Safety Systems**
   - Engineered Safeguards (ECCS), HPSI, LPSI flow rates
   - Passive safety systems if applicable
   - Setpoints for automatic actuation

---

## Recommended pom.xml Additions

```xml
<!-- Numerical Computing -->
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-math3</artifactId>
    <version>3.6.1</version>
</dependency>

<!-- Optional: Matrix Operations -->
<dependency>
    <groupId>org.nd4j</groupId>
    <artifactId>nd4j-native-platform</artifactId>
    <version>1.0.0-M1.1</version>
</dependency>

<!-- FMI for Coupling -->
<dependency>
    <groupId>no.ntnu.idi.fmi4j</groupId>
    <artifactId>fmi4j</artifactId>
    <version>0.48</version>
</dependency>

<!-- PostgreSQL (Optional) -->
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>42.6.0</version>
</dependency>
```

---

## Key References

- **IAEA ONCORE**: Open-source nuclear codes framework - http://www.iaea.org/topics/nuclear-power-reactors/open-source-nuclear-code-for-reactor-analysis-oncore
- **ARMI Docs**: https://terrapower.github.io/armi/
- **ThermoPower**: https://github.com/casella/ThermoPower
- **SAM Code**: https://github.com/idaholab/sam
- **OpenMC**: https://docs.openmc.org/

---

## Notes

- **Real-time constraints**: For <100ms latency, use lumped models (point kinetics + 1-D T-H)
- **Validation**: Essential to compare against RELAP5 or real plant data
- **Modularity**: Build physics as services (neutronics service, T-H service, control service) to be independently testable
- **Testing**: Use benchmark cases (ANL, IAEA) to validate implementation
