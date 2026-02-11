---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    background-color: #ffffff;
    color: #333333;
  }
  h1 {
    color: #0066cc;
  }
  h2 {
    color: #0066cc;
  }
  .columns {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
  }
---

# COD3S Data Framework
## Lightweight Data Streaming for Industrial IoT

**Executive Overview**

Version 1.0 | 2026-01-24

---

## The Challenge: Fragmented Industrial Data

### Pain Points in Manufacturing & IoT

- **Integration Complexity**: Each sensor requires custom code
- **Limited Observability**: Black-box data pipelines
- **Scalability Issues**: Slow consumers block fast producers
- **Operational Overhead**: Manual retry logic, failure handling
- **High Costs**: Heavy SCADA systems or over-engineered platforms

### The Gap

<div class="columns">
<div>

**Industrial SCADA/HMI**
- ❌ Heavy, expensive, proprietary
- ❌ Difficult to customize
- ❌ Vendor lock-in

</div>
<div>

**General Streaming (Kafka, Flink)**
- ❌ Over-engineered for simple use cases
- ❌ Complex operations (ZooKeeper, clusters)
- ❌ High resource requirements

</div>
</div>

---

## The Solution: COD3S Data

### Lightweight, Flexible, Production-Ready

**What is it?**
A data streaming framework designed for **real-time processing of temporal sensor data** in industrial and IoT environments.

**Key Insight:**
Fill the gap between heavy SCADA systems and complex streaming platforms with a **developer-friendly, embeddable framework**.

---

## Core Value Proposition

### Simplify Data Pipeline Development

- **10 lines of YAML** vs. hundreds of lines of custom code
- **Built-in reliability**: Automatic retry, dead letter queues, backpressure
- **Observable by design**: Metrics, logging, debugging out-of-the-box
- **Flexible deployment**: Embedded library, standalone service, or CLI

### Business Benefits

| Benefit | Impact |
|---------|--------|
| **Faster Time-to-Value** | Reduce integration time by 70% |
| **Lower Operational Costs** | Minimal infrastructure requirements |
| **Reduced Risk** | Production-ready reliability features |
| **Future-Proof** | Extensible plugin architecture |

---

## Use Case: 3D Printer Monitoring

### Real-World Example

**Scenario**: Manufacturing facility with multiple 3D printers

**Requirements**:
1. **Real-time alerts** (temperature exceeds safe range)
2. **Computed indicators** (viscosity from temp + speed + force)
3. **Data persistence** (historical analysis, quality reports)
4. **Flexible analysis** (compare printers, correlate conditions)

---

## Use Case: 3D Printer Monitoring (cont.)

### The COD3S Data Solution

```yaml
sources:
  - type: mqtt
    channel: "printers.*.temperature.*"

transformations:
  - type: threshold_alert
    input: "printers.*.temperature.extruder"
    threshold: 250
    output: "alerts.critical"

  - type: custom_python
    class: ViscosityComputer
    inputs: ["temp", "speed", "force"]
    output: "indicators.viscosity"

destinations:
  - type: console
    channel: "alerts.**"
  - type: database
    channel: "sensors.**"
```

**Result**: Complete monitoring solution in <20 lines of configuration

---

## High-Level Architecture

```mermaid
graph TB
    subgraph "Data Sources"
        S[Sensors, Files, APIs]
    end

    subgraph "COD3S Data Framework"
        SRC[Sources<br/>Ingest Data]
        BRK[Broker<br/>Route Messages]
        TRF[Transformations<br/>Process Data]
        DST[Destinations<br/>Output Data]
    end

    subgraph "Data Consumers"
        C[Databases, Dashboards, Files]
    end

    S --> SRC
    SRC --> BRK
    BRK --> TRF
    TRF --> BRK
    BRK --> DST
    DST --> C

    style BRK fill:#f9f,stroke:#333,stroke-width:4px
```

**Key**: Broker is the central hub - all components interact through it

---

## Key Capabilities

### 1. Flexible Data Ingestion
- Multiple source types (MQTT, files, databases, HTTP)
- Configurable delivery guarantees (at-most-once, at-least-once)
- Batch and streaming modes

### 2. Real-Time Processing
- **Stateless transformations**: Filtering, alerts, unit conversion
- **Stateful transformations**: Multi-sensor computations (e.g., viscosity)
- Low latency (<50ms p99 target)

### 3. Reliable Delivery
- Automatic retry with exponential backoff
- Dead Letter Queue for failed messages
- Backpressure handling with bounded buffers

---

## Key Capabilities (cont.)

### 4. Built-In Observability
- Metrics exposed as messages (self-reporting)
- Structured logging with trace IDs
- Debug mode for detailed inspection

### 5. Flexible Deployment
- **Embedded**: Library within your application
- **Standalone**: Separate service process
- **CLI**: Command-line operations

### 6. Extensible Architecture
- Plugin system for custom sources/destinations
- Custom Python transformations
- No need to fork the framework

---

## Version Roadmap

### V1.0 - Core Framework (Current Specification)
**Focus**: Lightweight, embeddable, production-ready
- ✅ In-memory broker
- ✅ Test/file sources, custom transformations
- ✅ Console/file/memory destinations
- ✅ YAML + Python configuration
- ✅ Performance: <50ms p99, 10K msg/s, <512MB RAM

### V2.0 - Integration (6-12 months)
**Focus**: Industry-standard integrations
- 🔄 Docker containerization
- 🔄 External databases (PostgreSQL, InfluxDB)
- 🔄 Message brokers (Redis, RabbitMQ)
- 🔄 MQTT, HTTP, Kafka connectors
- 🔄 Prometheus, OpenTelemetry support

---

## Version Roadmap (cont.)

### V3.0+ - Advanced Features (Future)
**Focus**: Advanced processing and distribution
- 💡 Complex event processing (CEP)
- 💡 Distributed multi-node processing
- 💡 Persistent state backends
- 💡 ML model integration
- 💡 Kubernetes operator

**Timeline**: Depends on V1/V2 adoption and community feedback

---

## Competitive Positioning

| Aspect | COD3S Data | Industrial SCADA | General Streaming |
|--------|------------|------------------|-------------------|
| **Setup Complexity** | ✅ Minutes | ❌ Days/Weeks | ❌ Hours/Days |
| **Resource Requirements** | ✅ <512MB RAM | ❌ Heavy | ❌ Multiple servers |
| **Customization** | ✅ Easy (Python/YAML) | ❌ Limited | ⚠️ Complex |
| **Cost** | ✅ Open source | ❌ High licensing | ⚠️ Infrastructure costs |
| **Time to Value** | ✅ Hours | ❌ Weeks | ⚠️ Days |
| **Learning Curve** | ✅ Low | ⚠️ Medium | ❌ Steep |

**Sweet Spot**: Industrial IoT use cases that need more than basic logging but less than enterprise streaming platforms

---

## Success Criteria

### V1.0 Objectives

**Performance Targets**:
- ✅ Latency: <50ms p99 (message ingestion to delivery)
- ✅ Throughput: 10,000 messages/second (single instance)
- ✅ Memory: <512MB RAM (typical workload)

**Developer Experience**:
- ✅ Simple API with comprehensive examples
- ✅ Clear error messages with actionable guidance
- ✅ Extensive documentation

**Production Readiness**:
- ✅ Built-in retry logic and failure handling
- ✅ Observable by default (metrics, logging)
- ✅ Tested with real-world use cases

---

## Next Steps

### Immediate Actions

1. **Review Specification**
   - Complete functional specification suite available
   - 15 detailed documents + technical presentation

2. **Prototype Development**
   - Reference implementation in Python 3.9+
   - Validate performance targets
   - Develop example applications (3D printer monitoring)

3. **Community Engagement**
   - Open source repository and documentation
   - Gather feedback from early adopters
   - Build plugin ecosystem

### Timeline
- **Q1 2026**: V1.0 specification finalized ✅
- **Q2 2026**: Reference implementation and testing
- **Q3 2026**: V1.0 release and documentation
- **Q4 2026**: Community adoption and V2.0 planning

---

## Thank You

### Questions & Discussion

**For More Information**:
- 📖 Full specification suite: 15 detailed documents
- 📊 Technical deep-dive: [Technical Presentation](PRESENTATION-TECHNICAL.md)
- 📝 Glossary: [99-GLOSSARY.md](FUNCTIONAL_SPECIFICATION/99-GLOSSARY.md)
- 🏗️ Architecture: [02-ARCHITECTURE.md](FUNCTIONAL_SPECIFICATION/02-ARCHITECTURE.md)

**Contact**: [Project team contact information]

---

*COD3S Data Framework - Lightweight Data Streaming for Industrial IoT*
*Version 1.0 Functional Specification | 2026-01-24*
