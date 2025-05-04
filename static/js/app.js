// DOM elements
document.addEventListener('DOMContentLoaded', function () {
    // Initialize all elements and event listeners
    initApp();
});

function initApp() {
    // Get DOM elements
    const chatMessages = document.getElementById('chat-messages');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const questionsList = document.getElementById('questions-list');
    const typingIndicator = document.getElementById('typing-indicator');
    const errorMessage = document.getElementById('error-message');
    const micButton = document.getElementById('mic-button');
    const listeningIndicator = document.getElementById('listening-indicator');
    const voiceModeToggle = document.getElementById('voice-mode');
    const continuousIndicator = document.getElementById('continuous-indicator');
    const audioVisualizer = document.getElementById('audio-visualizer');
    const visualizerBars = document.getElementById('visualizer-bars');

    // Initialize visualizer bars
    const NUM_BARS = 20;
    for (let i = 0; i < NUM_BARS; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        visualizerBars.appendChild(bar);
    }
    const visualizerBarElements = document.querySelectorAll('.visualizer-bar');

    // Speech recognition and TTS variables
    let isRecognizing = false;
    let currentRecognitionId = null;
    let isSpeaking = false;
    let currentAudioElement = null;

    // WebSocket variables
    let socket = null;
    let isSocketConnected = false;
    let isSocketAuthenticated = false;
    let reconnectAttempts = 0;
    let maxReconnectAttempts = 5;
    let reconnectInterval = 3000; // 3 seconds
    let reconnectTimer = null;
    let socketSessionId = null;

    // UI state refresh interval - fallback when WebSocket isn't available
    let uiStateRefreshInterval = null;

    // Add initial bot message
    addBotMessage("Hi! I'm your Active Recall Study Assistant. Tell me what topic you'd like to review today, and I'll help you practice with targeted questions.");

    // Initialize app state
    initializeAppState();

    // Event listeners
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Voice control event listeners
    micButton.addEventListener('click', toggleSpeechRecognition);
    voiceModeToggle.addEventListener('change', function () {
        savePreference('auto_read', this.checked);
    });

    // Clean up audio resources on page unload
    window.addEventListener('beforeunload', function () {
        stopSpeechRecognition();
        cancelOngoingTts();
        if (socket) {
            socket.disconnect();
        }
    });

    // Initialize app state from server
    async function initializeAppState() {
        try {
            // Initialize WebSocket connection
            initializeWebSocketConnection();

            // Also start UI state refresh as fallback
            startUIStateRefresh();

            // Load voice preferences
            await loadPreferences();

            console.log("App state initialized");
        } catch (error) {
            console.error("Error initializing app state:", error);
            showError("Error initializing app. Please refresh the page.");
        }
    }

    // Initialize WebSocket connection
    function initializeWebSocketConnection() {
        try {
            // Check if Socket.IO is available
            if (typeof io === 'undefined') {
                console.error("Socket.IO not available");
                return;
            }

            // Create socket connection
            console.log("Initializing WebSocket connection");
            socket = io(window.location.origin, {
                transports: ['websocket'],
                autoConnect: true,
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 1000
            });

            // Set up event handlers
            socket.on('connect', handleSocketConnect);
            socket.on('disconnect', handleSocketDisconnect);
            socket.on('connection_status', handleConnectionStatus);
            socket.on('authentication_status', handleAuthenticationStatus);
            socket.on('ui_state_update', handleUIStateUpdate);
            socket.on('tts_status_update', handleTTSStatusUpdate);
            socket.on('question_state_update', handleQuestionStateUpdate);

            console.log("WebSocket event handlers registered");
        } catch (error) {
            console.error("Error initializing WebSocket:", error);
        }
    }

    // Handle WebSocket connect event
    function handleSocketConnect() {
        console.log("WebSocket connected");
        isSocketConnected = true;
        reconnectAttempts = 0;

        // Authenticate with server
        authenticateWebSocket();
    }

    // Handle WebSocket disconnect event
    function handleSocketDisconnect() {
        console.log("WebSocket disconnected");
        isSocketConnected = false;
        isSocketAuthenticated = false;

        // Try to reconnect if not too many attempts
        if (reconnectAttempts < maxReconnectAttempts) {
            console.log(`Scheduling reconnect attempt ${reconnectAttempts + 1}/${maxReconnectAttempts}`);

            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
            }

            reconnectTimer = setTimeout(() => {
                reconnectAttempts++;
                console.log(`Attempting to reconnect (${reconnectAttempts}/${maxReconnectAttempts})`);
                socket.connect();
            }, reconnectInterval);
        } else {
            console.error("Max reconnect attempts reached, giving up");

            // Fallback to polling if WebSocket failed
            if (!uiStateRefreshInterval) {
                console.log("Falling back to polling for UI state");
                startUIStateRefresh();
            }
        }
    }

    // Handle connection status message
    function handleConnectionStatus(data) {
        console.log("Connection status:", data);
        if (data.status === 'connected') {
            socketSessionId = data.sid;
        }
    }

    // Authenticate WebSocket with server
    async function authenticateWebSocket() {
        try {
            if (!socket || !isSocketConnected) {
                console.error("Cannot authenticate: Socket not connected");
                return;
            }

            // Get WebSocket token
            const response = await fetch('/audio/websocket-token');
            if (!response.ok) {
                throw new Error(`Error fetching WebSocket token: ${response.status}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }

            // Send authentication request
            const token = data.token;
            const sessionId = getCookie('session');

            console.log("Authenticating WebSocket...");
            socket.emit('authenticate', {
                token: token,
                session_id: sessionId
            });

        } catch (error) {
            console.error("Error authenticating WebSocket:", error);
        }
    }

    // Handle authentication status message
    function handleAuthenticationStatus(data) {
        console.log("Authentication status:", data);

        if (data.status === 'success') {
            isSocketAuthenticated = true;

            // Request initial state
            requestUIState();
            requestTTSStatus();
            requestQuestionState();

            console.log("WebSocket authenticated successfully");
        } else {
            isSocketAuthenticated = false;
            console.error("WebSocket authentication failed:", data.message);
        }
    }

    // Handle UI state update
    function handleUIStateUpdate(uiState) {
        console.log("Received UI state update from WebSocket");
        updateUIFromState(uiState);
    }

    // Handle TTS status update
    function handleTTSStatusUpdate(ttsStatus) {
        console.log("Received TTS status update from WebSocket:", ttsStatus);

        // Update UI based on TTS status
        isSpeaking = ttsStatus.is_playing;
        let speakingIndicator = document.getElementById('speaking-indicator');

        if (isSpeaking) {
            if (!speakingIndicator) {
                speakingIndicator = document.createElement('div');
                speakingIndicator.id = 'speaking-indicator';
                speakingIndicator.className = 'speaking-indicator';
                speakingIndicator.textContent = 'Assistant is speaking...';
                document.body.appendChild(speakingIndicator);
            }
            speakingIndicator.style.display = 'block';
        } else if (speakingIndicator) {
            speakingIndicator.style.display = 'none';
        }
    }

    // Handle question state update
    function handleQuestionStateUpdate(questionStateData) {
        console.log("Received question state update from WebSocket:", questionStateData);

        // Update UI based on question state
        if (questionStateData.current_question) {
            // Update the UI to reflect the current question if needed
        }
    }

    // Request UI state via WebSocket
    function requestUIState() {
        if (socket && isSocketConnected && isSocketAuthenticated) {
            socket.emit('ui_state_request');
        }
    }

    // Request TTS status via WebSocket
    function requestTTSStatus() {
        if (socket && isSocketConnected && isSocketAuthenticated) {
            socket.emit('tts_status_request');
        }
    }

    // Request question state via WebSocket
    function requestQuestionState() {
        if (socket && isSocketConnected && isSocketAuthenticated) {
            socket.emit('question_state_request');
        }
    }

    // Get cookie value by name
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    // Start refreshing UI state periodically (fallback)
    function startUIStateRefresh() {
        // Initial refresh
        refreshUIState();

        // Set up interval for periodic refresh (every 2 seconds)
        if (!uiStateRefreshInterval) {
            uiStateRefreshInterval = setInterval(refreshUIState, 2000);
        }
    }

    // Stop UI state refresh
    function stopUIStateRefresh() {
        if (uiStateRefreshInterval) {
            clearInterval(uiStateRefreshInterval);
            uiStateRefreshInterval = null;
        }
    }

    // Refresh UI state from server (fallback)
    async function refreshUIState() {
        // Skip if WebSocket is active and authenticated
        if (socket && isSocketConnected && isSocketAuthenticated) {
            return;
        }

        try {
            const response = await fetch('/ui-state');
            if (!response.ok) {
                throw new Error(`Error fetching UI state: ${response.status}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }

            const uiState = data.ui_state;

            // Update UI based on state
            updateUIFromState(uiState);

        } catch (error) {
            console.error("Error refreshing UI state:", error);
            // Don't show error to user every time, just log it
        }
    }

    // Update UI elements based on state
    function updateUIFromState(uiState) {
        // Update microphone status
        if (uiState.is_microphone_active !== isRecognizing) {
            isRecognizing = uiState.is_microphone_active;
            if (isRecognizing) {
                micButton.classList.add('listening');
                listeningIndicator.style.display = 'inline';
            } else {
                micButton.classList.remove('listening');
                listeningIndicator.style.display = 'none';
            }
        }

        // Update continuous mode
        if (uiState.is_continuous_listening) {
            micButton.classList.add('continuous');
            continuousIndicator.style.display = 'block';
        } else {
            micButton.classList.remove('continuous');
            continuousIndicator.style.display = 'none';
        }

        // Update speaking status
        if (uiState.is_assistant_speaking !== isSpeaking) {
            isSpeaking = uiState.is_assistant_speaking;
            let speakingIndicator = document.getElementById('speaking-indicator');
            if (isSpeaking) {
                if (!speakingIndicator) {
                    speakingIndicator = document.createElement('div');
                    speakingIndicator.id = 'speaking-indicator';
                    speakingIndicator.className = 'speaking-indicator';
                    speakingIndicator.textContent = 'Assistant is speaking...';
                    document.body.appendChild(speakingIndicator);
                }
                speakingIndicator.style.display = 'block';
            } else if (speakingIndicator) {
                speakingIndicator.style.display = 'none';
            }
        }

        // Update visualizer settings
        if (uiState.visualizer_settings) {
            updateVisualizerSettings(uiState.visualizer_settings);
        }
    }

    // Update visualizer appearance
    function updateVisualizerSettings(settings) {
        if (settings.color) {
            visualizerBarElements.forEach(bar => {
                bar.style.backgroundColor = settings.color;
            });
        }
    }

    // Load preferences from server
    async function loadPreferences() {
        try {
            const response = await fetch('/text-to-speech/preferences');
            if (!response.ok) {
                throw new Error(`Error fetching preferences: ${response.status}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }

            const preferences = data.preferences;

            // Update UI based on preferences
            voiceModeToggle.checked = preferences.auto_read;

            console.log("Loaded preferences:", preferences);

        } catch (error) {
            console.error("Error loading preferences:", error);
            showError("Error loading preferences. Using defaults.");
        }
    }

    // Save a preference to the server
    async function savePreference(key, value) {
        try {
            const response = await fetch('/text-to-speech/preferences', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    [key]: value
                })
            });

            if (!response.ok) {
                throw new Error(`Error saving preference: ${response.status}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }

            console.log(`Preference ${key} saved:`, value);

        } catch (error) {
            console.error("Error saving preference:", error);
            showError("Error saving preference. Please try again.");
        }
    }

    // Toggle speech recognition
    async function toggleSpeechRecognition() {
        if (isRecognizing) {
            await stopSpeechRecognition();
        } else {
            await startSpeechRecognition();
        }
    }

    // Start speech recognition
    async function startSpeechRecognition() {
        try {
            // Show permission request indicator
            micButton.classList.add('requesting');
            micButton.innerHTML = '<i>⏳</i>';  // Hour glass icon
            showError('Requesting microphone access...', 0);

            // First ensure we have microphone permission
            console.log("Requesting microphone access...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // Stop the test stream
            stream.getTracks().forEach(track => track.stop());

            // Reset permission indicator
            micButton.classList.remove('requesting');
            micButton.innerHTML = '<i>🎤</i>';
            errorMessage.style.display = 'none';

            // Request the server to start listening
            const response = await fetch('/audio/speech-to-text/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    continuous: true,
                    mode: 'conversation'
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error');
            }

            // Store the recognition ID
            currentRecognitionId = data.recognition_id;
            console.log(`Started speech recognition with ID: ${currentRecognitionId}`);

            // Show the audio visualizer
            audioVisualizer.style.display = 'block';

            // Start recording and sending chunks
            await startAudioCapture();

        } catch (error) {
            // Reset indicators
            micButton.classList.remove('requesting');
            micButton.innerHTML = '<i>🎤</i>';

            console.error("Error starting speech recognition:", error);
            showError(`Microphone error: ${error.message}`);

            // Reset state
            isRecognizing = false;
        }
    }

    // Stop speech recognition
    async function stopSpeechRecognition() {
        try {
            if (!isRecognizing) return;

            // Stop audio capture
            stopAudioCapture();

            // Request the server to stop listening
            const response = await fetch('/audio/speech-to-text/stop', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    recognition_id: currentRecognitionId
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            console.log("Stopped speech recognition");

            // Hide the audio visualizer
            audioVisualizer.style.display = 'none';

            // Reset visualizer bars
            visualizerBarElements.forEach(bar => {
                bar.style.height = '3px';
            });

            // Reset state
            currentRecognitionId = null;

        } catch (error) {
            console.error("Error stopping speech recognition:", error);
        }
    }

    // Audio recording variables
    let mediaRecorder = null;
    let audioContext = null;
    let analyser = null;
    let microphone = null;
    let recordingInterval = null;

    // Start capturing audio and sending to server
    async function startAudioCapture() {
        try {
            // Initialize audio context for visualizer
            if (!initializeAudioContext()) {
                throw new Error("Failed to initialize audio context");
            }

            // Get high-quality audio stream
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 48000,
                    channelCount: 1 // Mono for speech
                }
            });

            console.log("Audio stream obtained successfully");

            // Store stream for later cleanup
            window.currentAudioStream = stream;

            // Connect to visualizer
            microphone = audioContext.createMediaStreamSource(stream);
            microphone.connect(analyser);

            // Find supported format
            const mimeTypes = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/ogg;codecs=opus',
                'audio/mp4;codecs=opus'
            ];

            let mediaRecorderOptions;
            for (const mimeType of mimeTypes) {
                if (MediaRecorder.isTypeSupported(mimeType)) {
                    mediaRecorderOptions = {
                        mimeType: mimeType,
                        audioBitsPerSecond: 128000
                    };
                    console.log(`Using format: ${mimeType}`);
                    break;
                }
            }

            // Create recorder
            if (mediaRecorderOptions) {
                mediaRecorder = new MediaRecorder(stream, mediaRecorderOptions);
            } else {
                mediaRecorder = new MediaRecorder(stream);
            }

            // Handle data available event
            mediaRecorder.ondataavailable = async (event) => {
                if (event.data.size > 0) {
                    await sendAudioChunk(event.data);
                }
            };

            // Start recording and request data every 2 seconds
            mediaRecorder.start(2000);
            console.log("MediaRecorder started");

            // Start visualizer updates
            if (recordingInterval) clearInterval(recordingInterval);
            recordingInterval = setInterval(updateVisualizer, 100);

            return true;

        } catch (error) {
            console.error("Error starting audio capture:", error);
            showError(`Microphone error: ${error.message}`);
            return false;
        }
    }

    // Stop audio capture
    function stopAudioCapture() {
        try {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
            }

            if (recordingInterval) {
                clearInterval(recordingInterval);
                recordingInterval = null;
            }

            // Stop all audio tracks
            if (window.currentAudioStream) {
                window.currentAudioStream.getTracks().forEach(track => track.stop());
            }

            // Disconnect microphone
            if (microphone) {
                microphone.disconnect();
                microphone = null;
            }

        } catch (error) {
            console.error("Error stopping audio capture:", error);
        }
    }

    // Send audio chunk to server
    async function sendAudioChunk(audioBlob) {
        try {
            if (!currentRecognitionId) return;

            const formData = new FormData();
            formData.append('audio_chunk', audioBlob, 'chunk.webm');
            formData.append('recognition_id', currentRecognitionId);

            const response = await fetch('/audio/speech-to-text/chunk', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();

            if (data.success && data.text) {
                console.log("Transcription received:", data.text);

                // If we got a valid transcription, process it
                if (data.is_final) {
                    processVoiceInput(data.text);
                }
            }

        } catch (error) {
            console.error("Error sending audio chunk:", error);
        }
    }

    // Initialize audio context for visualizer
    function initializeAudioContext() {
        try {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();

                if (audioContext.state === 'suspended') {
                    audioContext.resume();
                }
            } else if (audioContext.state === 'suspended') {
                audioContext.resume();
            }

            if (!analyser) {
                analyser = audioContext.createAnalyser();
                analyser.fftSize = 256;
            }

            return true;

        } catch (error) {
            console.error("Error initializing audio context:", error);
            showError(`Audio initialization error: ${error.message}`);
            return false;
        }
    }

    // Update the visualizer based on audio levels
    function updateVisualizer() {
        if (!analyser) return;

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteFrequencyData(dataArray);

        // Calculate average level for visualization
        const average = dataArray.reduce((sum, value) => sum + value, 0) / bufferLength;

        // Update each bar with some variation
        visualizerBarElements.forEach((bar, index) => {
            const variation = 0.4 + Math.sin(index * 0.2) * 0.2;
            const value = average * variation;
            const height = Math.max(3, Math.min(40, value * 0.4));
            bar.style.height = `${height}px`;
        });
    }

    // Process voice input
    function processVoiceInput(transcript) {
        if (!transcript.trim()) return;

        // Check for voice commands
        const lowerTranscript = transcript.toLowerCase();

        // Handle specific voice commands
        if (lowerTranscript.match(/^(next|next question|show next|try next|give me the next)(\s|$)/)) {
            getNextQuestion();
            return;
        } else if (lowerTranscript.match(/^(repeat|say again|what did you say|can you repeat that)(\s|$)/)) {
            repeatLastMessage();
            return;
        } else if (lowerTranscript.match(/^(stop listening|turn off voice|exit voice|end voice)(\s|$)/)) {
            stopSpeechRecognition();
            return;
        } else if (lowerTranscript.match(/^(clear|clear chat|start over|start fresh|reset|reset chat)(\s|$)/)) {
            clearChat();
            return;
        }

        // For all other input, send as a message
        userInput.value = transcript;
        sendMessage();
    }

    // Get next question
    async function getNextQuestion() {
        try {
            const response = await fetch('/questions/state', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    action: 'next'
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                if (data.question) {
                    const message = `Let's try this question: ${data.question}`;

                    // If the server didn't already add this, add it
                    // (Server should have added it to the chat history)
                    const lastMessages = document.querySelectorAll('.bot-message');
                    const lastMessage = lastMessages[lastMessages.length - 1]?.textContent;

                    if (!lastMessage || !lastMessage.includes(data.question)) {
                        addBotMessage(message);
                    }

                    // Speak the question if auto-read is enabled
                    const preferencesResponse = await fetch('/text-to-speech/preferences');
                    const preferences = await preferencesResponse.json();

                    if (preferences.success && preferences.preferences.auto_read) {
                        speakText(data.question);
                    }
                }
            } else {
                throw new Error(data.error || 'Failed to get next question');
            }

        } catch (error) {
            console.error("Error getting next question:", error);
            showError(`Error: ${error.message}`);
        }
    }

    // Repeat last bot message
    function repeatLastMessage() {
        const botMessages = document.querySelectorAll('.bot-message');
        if (botMessages.length > 0) {
            const lastMessage = botMessages[botMessages.length - 1].textContent;
            speakText(lastMessage);
        }
    }

    // Clear chat
    function clearChat() {
        chatMessages.innerHTML = '';
        addBotMessage("Chat cleared. What would you like to discuss now?");
    }

    // Send message to server
    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        // Add user message to chat
        addUserMessage(message);
        userInput.value = '';

        // Show typing indicator
        typingIndicator.style.display = 'block';
        errorMessage.style.display = 'none';

        // Temporarily pause voice recording during API call
        const wasRecognizing = isRecognizing;
        if (wasRecognizing) {
            try {
                await stopSpeechRecognition();
            } catch (e) {
                console.error("Error pausing recording:", e);
            }
        }

        try {
            // Send to server
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: message })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();

            // Hide typing indicator
            typingIndicator.style.display = 'none';

            if (data.error) {
                showError(data.error);
                return;
            }

            // Add bot response
            addBotMessage(data.response);

            // Check if we should speak the response
            const preferencesResponse = await fetch('/text-to-speech/preferences');
            const preferences = await preferencesResponse.json();

            if (preferences.success && preferences.preferences.auto_read) {
                speakText(data.response);
            }

            // Update questions if provided
            if (data.questions && data.questions.length > 0) {
                updateQuestions(data.questions);
            }

        } catch (error) {
            typingIndicator.style.display = 'none';
            showError('An error occurred. Please try again.');
            console.error('Error:', error);
        } finally {
            // Resume voice recording if it was active before
            if (wasRecognizing) {
                setTimeout(() => {
                    startSpeechRecognition();
                }, 1000);
            }
        }
    }

    // Add user message to chat
    function addUserMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user-message';
        messageDiv.textContent = text;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Add bot message to chat
    function addBotMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';
        messageDiv.textContent = text;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // Add a "Listen" button for text-to-speech
        const listenButton = document.createElement('button');
        listenButton.className = 'listen-button';
        listenButton.innerHTML = '🔊';
        listenButton.title = 'Listen';
        listenButton.style.marginLeft = '5px';
        listenButton.style.padding = '2px 5px';
        listenButton.style.fontSize = '12px';
        listenButton.style.backgroundColor = '#3498db';
        listenButton.style.color = 'white';
        listenButton.style.border = 'none';
        listenButton.style.borderRadius = '3px';
        listenButton.style.cursor = 'pointer';

        listenButton.addEventListener('click', function () {
            speakText(text);
        });

        messageDiv.appendChild(listenButton);
    }

    // Update questions list
    function updateQuestions(questions) {
        questionsList.innerHTML = '';

        questions.forEach((question, index) => {
            const questionDiv = document.createElement('div');
            questionDiv.className = 'question';
            questionDiv.setAttribute('data-question-index', index);

            const questionText = document.createElement('p');
            questionText.innerHTML = `<strong>Q${index + 1}:</strong> ${question}`;
            questionDiv.appendChild(questionText);

            // Add audio icon to listen to the question
            const listenButton = document.createElement('button');
            listenButton.innerHTML = '🔊';
            listenButton.title = 'Listen';
            listenButton.style.marginLeft = '5px';
            listenButton.style.padding = '2px 5px';
            listenButton.style.fontSize = '12px';
            listenButton.style.background = 'none';
            listenButton.style.border = 'none';
            listenButton.style.cursor = 'pointer';

            listenButton.addEventListener('click', function (e) {
                e.stopPropagation(); // Prevent triggering question click
                speakText(question);
            });

            questionText.appendChild(listenButton);

            // Add functionality to click on a question
            questionDiv.addEventListener('click', function () {
                askQuestion(question, index);
            });

            questionsList.appendChild(questionDiv);
        });
    }

    // Ask a question
    function askQuestion(question, index) {
        // Add a button for the bot to ask this specific question
        const askButton = document.createElement('button');
        askButton.className = 'ask-question-button';
        askButton.textContent = 'Next Question';
        askButton.setAttribute('data-index', index);

        askButton.addEventListener('click', function () {
            // Remove this button after clicking
            this.remove();
            getNextQuestion();
        });

        // Add button to the chat
        chatMessages.appendChild(askButton);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Speak text using TTS
    async function speakText(text) {
        try {
            console.log("Adding to TTS queue:", text.substring(0, 50) + "...");

            // Cancel any ongoing TTS first
            await cancelOngoingTts();

            // Add to TTS queue
            const response = await fetch('/text-to-speech/queue', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    priority: 'normal'
                })
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Failed to queue TTS');
            }

            console.log(`Added to TTS queue, position: ${data.queue_position + 1}/${data.queue_length}`);

            // Process the queue
            await processQueue();

        } catch (error) {
            console.error("Error in speakText:", error);
            showError(`TTS error: ${error.message}`);
        }
    }

    // Process TTS queue
    async function processQueue() {
        try {
            const response = await fetch('/text-to-speech/process-queue', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            // For streaming audio, the response will be a blob
            const contentType = response.headers.get('content-type');

            if (contentType && contentType.includes('audio')) {
                // Handle audio response
                const audioBlob = await response.blob();
                const audioUrl = URL.createObjectURL(audioBlob);

                // Create and play audio element
                const audioElement = new Audio(audioUrl);
                currentAudioElement = audioElement;

                // Set up completion handling
                audioElement.onended = () => {
                    console.log("Audio playback completed");
                    URL.revokeObjectURL(audioUrl);
                    currentAudioElement = null;

                    // Process next item in queue if any
                    setTimeout(() => {
                        processQueue();
                    }, 500);
                };

                // Play the audio
                await audioElement.play();

            } else {
                // Handle JSON response (empty queue or error)
                const data = await response.json();

                if (!data.success) {
                    throw new Error(data.error || 'Failed to process TTS queue');
                }

                if (data.queue_empty) {
                    console.log("TTS queue is empty");
                }
            }

        } catch (error) {
            console.error("Error processing TTS queue:", error);
        }
    }

    // Cancel ongoing TTS
    async function cancelOngoingTts() {
        try {
            console.log("Cancelling ongoing TTS");

            // If we have an audio element, stop it
            if (currentAudioElement) {
                currentAudioElement.pause();
                currentAudioElement = null;
            }

            // Clear the server-side queue
            const response = await fetch('/text-to-speech/queue', {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error || 'Failed to cancel TTS');
            }

            console.log("TTS cancelled successfully");

        } catch (error) {
            console.error("Error cancelling TTS:", error);
        }
    }

    // Show error message
    function showError(message, timeout = 3000) {
        errorMessage.textContent = message;
        errorMessage.style.display = 'block';

        if (timeout > 0) {
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, timeout);
        }
    }
} 