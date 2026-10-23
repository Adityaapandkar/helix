// Function to handle stream events from the backend
const handleStreamEvent = (event: MessageEvent) => {
    try {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case "progress":
                setProgress(data.value);
                break;

            case "log":
                const logData = data.data;
                // Convert timestamp to Date object
                const timestamp = new Date(logData.timestamp * 1000);

                // Check if the agent has changed and update the view accordingly
                if (logData.agent !== currentAgent) {
                    setCurrentAgent(logData.agent);

                    // Map agent to view type and trigger view change
                    switch (logData.agent.toLowerCase()) {
                        case "analysis":
                            handleViewChange("analysis");
                            break;
                        case "binding":
                            handleViewChange("binding");
                            break;
                        case "molecule":
                            handleViewChange("molecule");
                            break;
                        case "docking":
                            handleViewChange("docking");
                            break;
                        // We don't automatically switch to structure view
                    }
                }

                setLogs((prevLogs) => [
                    ...prevLogs,
                    {
                        ...logData,
                        timestamp,
                    },
                ]);
                break;

            case "protein_properties":
                setProteinProperties(data.data);
                break;

            case "binding_sites":
                setBindingSites(data.data);
                break;

            case "molecule_properties":
                setMoleculeProperties(data.data);
                break;

            case "docking_results":
                setDockingResults(data.data);
                break;

            case "keep_alive":
                // Handle keep-alive messages - just log them if necessary
                console.log("Keep-alive received:", data.elapsed_seconds, "seconds elapsed");
                break;

            case "status_update":
                // Add the status update as a log entry
                setLogs((prevLogs) => [
                    ...prevLogs,
                    {
                        id: `status-${Date.now()}`,
                        timestamp: new Date(),
                        agent: "Orchestrator",
                        message: data.message,
                        type: "info"
                    },
                ]);
                break;

            case "complete":
                setIsRunning(false);
                // Close the stream
                if (streamSource) {
                    streamSource.close();
                    setStreamSource(null);
                }
                break;

            default:
                console.log("Unknown event type:", data.type);
        }
    } catch (error) {
        console.error("Error parsing event data:", error);
    }
}; 