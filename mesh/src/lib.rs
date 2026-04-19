//! skaal-mesh — Skaal distributed runtime mesh exposed to Python via PyO3.
//!
//! Provides cross-node agent routing, distributed channel publish/subscribe,
//! failure detection, and health reporting.  The mesh runs a Tokio runtime
//! internally so all I/O is async on the Rust side even though the Python
//! API is synchronous (blocking the calling thread).
//!
//! Designed to be built with `maturin` and imported as `import skaal_mesh`.

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tokio::runtime::Runtime;

// ── Node registry (in-process stand-in for gossip discovery) ────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
struct NodeInfo {
    node_id: String,
    address: String,
    functions: Vec<String>,
}

#[derive(Debug)]
struct MeshState {
    nodes: HashMap<String, NodeInfo>,
    channels: HashMap<String, Vec<String>>, // topic → [messages JSON]
    agent_locations: HashMap<String, String>, // "type:id" → node_id
}

impl MeshState {
    fn new() -> Self {
        Self {
            nodes: HashMap::new(),
            channels: HashMap::new(),
            agent_locations: HashMap::new(),
        }
    }
}

// ── Python-visible mesh handle ──────────────────────────────────────────────

/// The runtime mesh for a Skaal application.
///
/// Initialized from a plan.skaal.lock JSON string.  In production the mesh
/// uses gRPC (via tonic) to communicate between nodes; in local/test mode
/// all nodes live in-process and communicate through shared memory.
#[pyclass]
pub struct SkaalMesh {
    app_name: String,
    node_id: String,
    state: Arc<Mutex<MeshState>>,
    #[allow(dead_code)]
    rt: Arc<Runtime>,
}

#[pymethods]
impl SkaalMesh {
    /// Create a new SkaalMesh.
    ///
    /// Args:
    ///     app_name:   Application name (from ``App("name")``).
    ///     plan_json:  Serialized ``plan.skaal.lock`` content.
    ///     node_id:    Unique identifier for this mesh node (default: "node-0").
    #[new]
    #[pyo3(signature = (app_name, plan_json, node_id = None))]
    pub fn new(app_name: String, plan_json: String, node_id: Option<String>) -> PyResult<Self> {
        let nid = node_id.unwrap_or_else(|| "node-0".into());
        let state = Arc::new(Mutex::new(MeshState::new()));

        // Register self as a node.
        {
            let mut s = state.lock().unwrap();
            s.nodes.insert(
                nid.clone(),
                NodeInfo {
                    node_id: nid.clone(),
                    address: "local".into(),
                    functions: Vec::new(),
                },
            );
        }

        // Parse plan to extract function names so we know what this node serves.
        if let Ok(plan) = serde_json::from_str::<serde_json::Value>(&plan_json) {
            if let Some(compute) = plan.get("compute").and_then(|v| v.as_object()) {
                let mut s = state.lock().unwrap();
                if let Some(node) = s.nodes.get_mut(&nid) {
                    for key in compute.keys() {
                        node.functions.push(key.clone());
                    }
                }
            }
        }

        let rt = Arc::new(
            tokio::runtime::Builder::new_multi_thread()
                .worker_threads(2)
                .enable_all()
                .build()
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?,
        );

        Ok(Self {
            app_name,
            node_id: nid,
            state,
            rt,
        })
    }

    /// Register another node in the mesh (for local multi-node testing).
    #[pyo3(signature = (node_id, address, functions = None))]
    pub fn register_node(
        &self,
        node_id: String,
        address: String,
        functions: Option<Vec<String>>,
    ) -> PyResult<()> {
        let mut s = self.state.lock().unwrap();
        s.nodes.insert(
            node_id.clone(),
            NodeInfo {
                node_id,
                address,
                functions: functions.unwrap_or_default(),
            },
        );
        Ok(())
    }

    /// Route a function invocation to the best node that serves it.
    ///
    /// Returns: ``(node_id, result_json)`` where *result_json* is ``None``
    /// when the call must be forwarded to a remote node (the Python runtime
    /// handles the actual HTTP call).
    pub fn route_invoke(
        &self,
        function_name: &str,
        _args_json: &str,
    ) -> PyResult<(String, Option<String>)> {
        let s = self.state.lock().unwrap();

        // Prefer local node.
        if let Some(local) = s.nodes.get(&self.node_id) {
            if local.functions.contains(&function_name.to_string()) {
                // Local — caller should invoke directly; we return our own id + None.
                return Ok((self.node_id.clone(), None));
            }
        }

        // Find a remote node that serves this function.
        for (nid, info) in &s.nodes {
            if nid != &self.node_id && info.functions.contains(&function_name.to_string()) {
                return Ok((nid.clone(), None));
            }
        }

        Err(pyo3::exceptions::PyKeyError::new_err(format!(
            "no mesh node serves function '{function_name}'"
        )))
    }

    /// Route a message to an agent instance, activating it if necessary.
    ///
    /// Returns the node_id that owns (or should own) this agent instance.
    pub fn route_agent_call(
        &self,
        agent_type: &str,
        agent_id: &str,
        _method: &str,
        _args_json: &str,
    ) -> PyResult<String> {
        let key = format!("{agent_type}:{agent_id}");
        let mut s = self.state.lock().unwrap();

        // Check if agent is already placed.
        if let Some(nid) = s.agent_locations.get(&key) {
            return Ok(nid.clone());
        }

        // Place on the node with fewest agents (simple round-robin substitute).
        let mut counts: HashMap<&str, usize> = HashMap::new();
        for nid in s.nodes.keys() {
            counts.insert(nid, 0);
        }
        for nid in s.agent_locations.values() {
            if let Some(c) = counts.get_mut(nid.as_str()) {
                *c += 1;
            }
        }
        let target = counts
            .into_iter()
            .min_by_key(|&(_, c)| c)
            .map(|(nid, _)| nid.to_string())
            .unwrap_or_else(|| self.node_id.clone());

        s.agent_locations.insert(key, target.clone());
        Ok(target)
    }

    /// Publish a message to a distributed channel topic.
    pub fn channel_publish(&self, topic: &str, message_json: &str) -> PyResult<()> {
        let mut s = self.state.lock().unwrap();
        s.channels
            .entry(topic.to_string())
            .or_default()
            .push(message_json.to_string());
        Ok(())
    }

    /// Consume pending messages from a distributed channel topic.
    ///
    /// Returns a list of JSON strings and clears the buffer.
    pub fn channel_consume(&self, topic: &str) -> PyResult<Vec<String>> {
        let mut s = self.state.lock().unwrap();
        let msgs = s.channels.remove(topic).unwrap_or_default();
        Ok(msgs)
    }

    /// Return a JSON snapshot of mesh health.
    pub fn health_snapshot(&self) -> PyResult<String> {
        let s = self.state.lock().unwrap();
        let health = serde_json::json!({
            "app": self.app_name,
            "node_id": self.node_id,
            "status": "ok",
            "nodes": s.nodes.len(),
            "agents_placed": s.agent_locations.len(),
            "channel_topics": s.channels.len(),
        });
        Ok(health.to_string())
    }

    /// List all registered node IDs.
    pub fn list_nodes(&self) -> PyResult<Vec<String>> {
        let s = self.state.lock().unwrap();
        Ok(s.nodes.keys().cloned().collect())
    }

    /// Shut down the internal Tokio runtime gracefully.
    pub fn shutdown(&self) -> PyResult<()> {
        // The Arc<Runtime> drops when all references are gone; explicit
        // shutdown is a no-op here but provided for API completeness.
        Ok(())
    }
}

/// Python module entry point.
#[pymodule]
fn skaal_mesh(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SkaalMesh>()?;
    Ok(())
}
