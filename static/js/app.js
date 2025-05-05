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

    // Difficulty and progress elements
    const difficultyButtons = document.querySelectorAll('.difficulty-button');
    const difficultyDescription = document.getElementById('difficulty-description');
    const progressCount = document.getElementById('progress-count');
    const progressBar = document.getElementById('progress-bar');
    const accuracyPercent = document.getElementById('accuracy-percent');
    const nextQuestionButton = document.getElementById('next-question-button');
    const hintButton = document.getElementById('hint-button');
    const difficultyIndicator = document.getElementById('difficulty-indicator');
    const questionNumber = document.getElementById('question-number');
    const questionsInfo = document.getElementById('questions-info');

    // PDF Upload elements
    const pdfFileInput = document.getElementById('pdf-file-input');
    const pdfUploadButton = document.getElementById('pdf-upload-button');
    const pdfUploadStatus = document.getElementById('pdf-upload-status');
    const pdfProgressBar = document.getElementById('pdf-progress-bar');
    const pdfStatusMessage = document.getElementById('pdf-status-message');
    const questionSourceIndicator = document.getElementById('question-source-indicator');

    // Current state
    let currentDifficulty = 'mixed';
    let questionState = {
        currentIndex: 0,
        total: 0,
        correctCount: 0,
        incorrectCount: 0
    };

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

    // PDF Upload event listeners
    pdfUploadButton.addEventListener('click', handlePdfUpload);
    pdfFileInput.addEventListener('change', function () {
        // Enable/disable upload button based on file selection
        if (pdfFileInput.files.length > 0) {
            const file = pdfFileInput.files[0];
            if (file.type === 'application/pdf') {
                pdfUploadButton.disabled = false;
                pdfStatusMessage.textContent = `Selected: ${file.name}`;
                pdfUploadStatus.style.display = 'block';
            } else {
                pdfUploadButton.disabled = true;
                pdfStatusMessage.textContent = 'Please select a valid PDF file.';
                pdfUploadStatus.style.display = 'block';
            }
        } else {
            pdfUploadButton.disabled = true;
            pdfUploadStatus.style.display = 'none';
        }
    });

    // Difficulty button event listeners
    difficultyButtons.forEach(button => {
        button.addEventListener('click', function () {
            // Update active button
            difficultyButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');

            // Update current difficulty
            currentDifficulty = this.getAttribute('data-difficulty');

            // Update description
            updateDifficultyDescription(currentDifficulty);
        });
    });

    // Question control buttons
    nextQuestionButton.addEventListener('click', function () {
        sendMessage('next question');
    });

    hintButton.addEventListener('click', function () {
        sendMessage('hint');
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
            const isSecure = window.location.protocol === 'https:';
            const socketProtocol = isSecure ? 'wss://' : 'ws://';
            const socketUrl = socketProtocol + window.location.host;
            console.log(`Using WebSocket URL: ${socketUrl}`);

            socket = io(socketUrl, {
                transports: ['websocket'],
                autoConnect: true,
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 1000,
                secure: isSecure
            });

            // Set up event handlers
            socket.on('connect', handleSocketConnect);
            socket.on('disconnect', handleSocketDisconnect);
            socket.on('connection_status', handleConnectionStatus);
            socket.on('authentication_status', handleAuthenticationStatus);
            socket.on('ui_state_update', handleUIStateUpdate);
            socket.on('tts_status_update', handleTTSStatusUpdate);
            socket.on('question_state_update', handleQuestionStateUpdate);
            socket.on('connect_error', (error) => {
                console.error("WebSocket connection error:", error);
                showError("Connection error. Falling back to polling.");
                // Immediately start polling for UI state as a fallback
                startUIStateRefresh();
            });
            socket.on('error', (error) => {
                console.error("WebSocket error:", error);
                showError("WebSocket error. Falling back to polling.");
                // Immediately start polling for UI state as a fallback
                startUIStateRefresh();
            });

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

        // Handle PDF processing state
        if (uiState.is_processing_pdf) {
            pdfUploadStatus.style.display = 'block';
            pdfStatusMessage.textContent = `Processing PDF: ${uiState.pdf_filename || 'document'}...`;
            pdfProgressBar.style.width = '50%'; // Indeterminate progress
            pdfUploadButton.disabled = true;
        } else if (uiState.pdf_processed) {
            pdfUploadStatus.style.display = 'block';
            pdfStatusMessage.textContent = `PDF processed successfully: ${uiState.pdf_filename || 'document'}`;
            pdfProgressBar.style.width = '100%';
            pdfUploadButton.disabled = false;
        } else if (uiState.pdf_error) {
            pdfUploadStatus.style.display = 'block';
            pdfStatusMessage.textContent = `Error: ${uiState.pdf_error}`;
            pdfProgressBar.style.width = '0%';
            pdfUploadButton.disabled = false;
            showError(uiState.pdf_error);
        }
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
        const state = questionStateData.question_state || {};
        const currentQuestion = questionStateData.current_question;
        const totalQuestions = questionStateData.total_questions || 0;

        // Update local state
        questionState = {
            currentIndex: state.current_index || 0,
            total: state.total || totalQuestions,
            correctCount: state.correct_count || 0,
            incorrectCount: state.incorrect_count || 0,
            difficulty: state.difficulty || 'mixed'
        };

        // Enable/disable question controls
        updateQuestionControls(totalQuestions > 0);

        // Update progress display
        updateProgressDisplay(
            questionState.currentIndex,
            questionState.total,
            questionState.correctCount,
            questionState.incorrectCount
        );

        // Update difficulty indicator
        if (questionState.difficulty) {
            difficultyIndicator.textContent = questionState.difficulty.charAt(0).toUpperCase() +
                questionState.difficulty.slice(1);

            // Add difficulty class
            difficultyIndicator.className = ''; // Remove previous classes
            difficultyIndicator.classList.add(`difficulty-${questionState.difficulty}`);
        }

        // Update questions info
        if (totalQuestions > 0) {
            questionsInfo.textContent = `${totalQuestions} questions available for practice.`;
        } else {
            questionsInfo.textContent = 'After you specify a topic, active recall questions will appear here.';
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
        // Detect and process common voice commands
        const lowerTranscript = transcript.toLowerCase();

        // Command: Next question
        if (/^next(?: question)?$/i.test(lowerTranscript) ||
            /^(?:go to|give me) (?:the )?next question$/i.test(lowerTranscript)) {
            console.log("Voice command: Next question");
            sendMessage("next question");
            return;
        }

        // Command: Hint/Help
        if (/^(?:hint|help|give me a hint|help me)$/i.test(lowerTranscript)) {
            console.log("Voice command: Hint");
            sendMessage("hint");
            return;
        }

        // Command: Repeat 
        if (/^(?:repeat|say again|say that again)$/i.test(lowerTranscript)) {
            console.log("Voice command: Repeat");
            repeatLastMessage();
            return;
        }

        // Command: Clear chat
        if (/^(?:clear|clear chat|start over|reset)$/i.test(lowerTranscript)) {
            console.log("Voice command: Clear chat");
            clearChat();
            return;
        }

        // Command: Stop listening
        if (/^(?:stop listening|stop recording|turn off mic)$/i.test(lowerTranscript)) {
            console.log("Voice command: Stop listening");
            stopSpeechRecognition();
            return;
        }

        // Command: Change difficulty
        if (/(?:make it|set to|change to|switch to)(?: the)? (easy|basic|beginner|simple|intermediate|medium|moderate|hard|advanced|difficult|challenging|mixed) (?:difficulty|level|mode)/i.test(lowerTranscript)) {
            const match = lowerTranscript.match(/(?:make it|set to|change to|switch to)(?: the)? (easy|basic|beginner|simple|intermediate|medium|moderate|hard|advanced|difficult|challenging|mixed) (?:difficulty|level|mode)/i);
            if (match && match[1]) {
                let newDifficulty = 'mixed';
                const requestedLevel = match[1].toLowerCase();

                if (['easy', 'basic', 'beginner', 'simple'].includes(requestedLevel)) {
                    newDifficulty = 'basic';
                } else if (['intermediate', 'medium', 'moderate'].includes(requestedLevel)) {
                    newDifficulty = 'intermediate';
                } else if (['hard', 'advanced', 'difficult', 'challenging'].includes(requestedLevel)) {
                    newDifficulty = 'advanced';
                }

                console.log(`Voice command: Change difficulty to ${newDifficulty}`);

                // Update UI to reflect change
                difficultyButtons.forEach(btn => {
                    if (btn.getAttribute('data-difficulty') === newDifficulty) {
                        btn.click(); // Simulate click on the button
                    }
                });

                // Confirm the change verbally
                addBotMessage(`I've changed the difficulty level to ${newDifficulty}. What topic would you like to study?`);
                if (voiceModeToggle.checked) {
                    speakText(`I've changed the difficulty level to ${newDifficulty}. What topic would you like to study?`);
                }
                return;
            }
        }

        // Command: Make it easier/harder
        if (/make(?: it)? (easier|harder|more difficult|simpler)/i.test(lowerTranscript)) {
            const match = lowerTranscript.match(/make(?: it)? (easier|harder|more difficult|simpler)/i);
            if (match && match[1]) {
                const direction = match[1].toLowerCase();
                let newDifficulty = currentDifficulty;

                // Determine new difficulty based on current and direction
                if (['easier', 'simpler'].includes(direction)) {
                    if (currentDifficulty === 'advanced') newDifficulty = 'intermediate';
                    else if (currentDifficulty === 'intermediate') newDifficulty = 'basic';
                    else if (currentDifficulty === 'mixed') newDifficulty = 'basic';
                } else if (['harder', 'more difficult'].includes(direction)) {
                    if (currentDifficulty === 'basic') newDifficulty = 'intermediate';
                    else if (currentDifficulty === 'intermediate') newDifficulty = 'advanced';
                    else if (currentDifficulty === 'mixed') newDifficulty = 'advanced';
                }

                // Only process if there's an actual change
                if (newDifficulty !== currentDifficulty) {
                    console.log(`Voice command: Change difficulty from ${currentDifficulty} to ${newDifficulty}`);

                    // Update UI to reflect change
                    difficultyButtons.forEach(btn => {
                        if (btn.getAttribute('data-difficulty') === newDifficulty) {
                            btn.click(); // Simulate click on the button
                        }
                    });

                    // If we have a current topic, request new questions
                    if (questionState.total > 0) {
                        const message = `Change difficulty to ${newDifficulty}`;
                        sendMessage(message);
                    } else {
                        // Just confirm the change
                        addBotMessage(`I've changed the difficulty level to ${newDifficulty}. What topic would you like to study?`);
                        if (voiceModeToggle.checked) {
                            speakText(`I've changed the difficulty level to ${newDifficulty}. What topic would you like to study?`);
                        }
                    }
                    return;
                }
            }
        }

        // If no command was detected, treat as regular input
        console.log("Voice input (no command detected):", transcript);
        sendMessage(transcript);
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

    // Send a message to the server
    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        // Add difficulty info for topic requests
        let messageToSend = message;
        if (isNewTopicRequest(message)) {
            messageToSend = `${message} at ${currentDifficulty} difficulty`;
        }

        addUserMessage(message);
        userInput.value = '';
        typingIndicator.style.display = 'block';

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: messageToSend }),
            });

            if (!response.ok) {
                throw new Error(`Error: ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                showError(data.error);
                return;
            }

            addBotMessage(data.response);

            // Update questions if they were returned
            if (data.questions && data.questions.length > 0) {
                updateQuestions(data.questions);

                // Enable question controls
                updateQuestionControls(true);
            }

            // Auto-speak response if enabled
            if (voiceModeToggle.checked) {
                speakText(data.response);
            }

        } catch (error) {
            showError(`Failed to send message: ${error.message}`);
        } finally {
            typingIndicator.style.display = 'none';
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
        listenButton.innerHTML = '🔊 Listen';
        listenButton.title = 'Click to listen to this message';

        // Keep track if this button's audio is playing
        let isPlaying = false;

        listenButton.addEventListener('click', function () {
            if (isPlaying) {
                // If already playing, cancel it
                if (window.speechSynthesis) {
                    window.speechSynthesis.cancel();
                }
                this.innerHTML = '🔊 Listen';
                this.classList.remove('playing');
                isPlaying = false;
            } else {
                // Start new playback
                this.innerHTML = '⏹️ Stop';
                this.classList.add('playing');
                isPlaying = true;

                // Use browser TTS directly for more reliable playback
                if (window.speechSynthesis) {
                    const utterance = new SpeechSynthesisUtterance(text);

                    // Set utterance properties
                    utterance.rate = 1.0;
                    utterance.pitch = 1.0;
                    utterance.volume = 1.0;

                    // Get available voices - prefer female English voice if available
                    const voices = window.speechSynthesis.getVoices();
                    if (voices.length > 0) {
                        // Try to find a female English voice
                        const femaleEnglishVoices = voices.filter(voice =>
                            voice.lang.startsWith('en') && voice.name.includes('Female'));

                        if (femaleEnglishVoices.length > 0) {
                            utterance.voice = femaleEnglishVoices[0];
                        } else {
                            // Use any English voice
                            const englishVoices = voices.filter(voice => voice.lang.startsWith('en'));
                            if (englishVoices.length > 0) {
                                utterance.voice = englishVoices[0];
                            }
                        }
                    }

                    // Handle completion
                    utterance.onend = () => {
                        this.innerHTML = '🔊 Listen';
                        this.classList.remove('playing');
                        isPlaying = false;
                    };

                    // Handle errors
                    utterance.onerror = () => {
                        this.innerHTML = '🔊 Listen';
                        this.classList.remove('playing');
                        isPlaying = false;
                        showError("Text-to-speech failed");
                    };

                    // Start speaking
                    window.speechSynthesis.speak(utterance);
                } else {
                    // Try server TTS as fallback
                    speakText(text).then(() => {
                        this.innerHTML = '🔊 Listen';
                        this.classList.remove('playing');
                        isPlaying = false;
                    }).catch(() => {
                        this.innerHTML = '🔊 Listen';
                        this.classList.remove('playing');
                        isPlaying = false;
                        showError("Text-to-speech not available");
                    });
                }
            }
        });

        messageDiv.appendChild(listenButton);
    }

    // Update questions list with difficulty indicators
    function updateQuestions(questions) {
        // Clear previous questions
        questionsList.innerHTML = '';

        if (!questions || questions.length === 0) {
            // No questions available
            questionsList.innerHTML = '<p>No questions available yet.</p>';
            updateQuestionControls(false);
            return;
        }

        // Add each question with a button
        questions.forEach((question, index) => {
            const questionItem = document.createElement('div');
            questionItem.className = 'question-item';

            // Extract difficulty label if present
            let difficultyLabel = '';
            const difficultyMatch = question.match(/^\[(Basic|Intermediate|Advanced)\] /);
            if (difficultyMatch) {
                difficultyLabel = difficultyMatch[1];
            }

            const questionButton = document.createElement('button');
            questionButton.className = 'question-button';

            // Add difficulty indicator if available
            if (difficultyLabel) {
                const indicator = document.createElement('span');
                indicator.className = `difficulty-indicator difficulty-${difficultyLabel.toLowerCase()}`;
                indicator.textContent = difficultyLabel;
                questionButton.appendChild(indicator);

                // Remove the label from the actual question text for display
                question = question.replace(/^\[(Basic|Intermediate|Advanced)\] /, '');
            }

            const buttonText = document.createElement('span');
            buttonText.textContent = `Q${index + 1}: ${question.length > 60 ? question.substring(0, 60) + '...' : question}`;
            questionButton.appendChild(buttonText);

            questionButton.onclick = function () {
                askQuestion(question, index);
            };

            questionItem.appendChild(questionButton);
            questionsList.appendChild(questionItem);
        });

        // Update question controls
        updateQuestionControls(true);

        // Update progress display with initial values
        questionState.total = questions.length;
        updateProgressDisplay(0, questions.length, 0, 0);
    }

    // Ask a question
    function askQuestion(question, index) {
        // Highlight active question
        const questionItems = document.querySelectorAll('.question-item');
        questionItems.forEach((item, i) => {
            const button = item.querySelector('.question-button');
            if (i === index) {
                button.classList.add('active');
            } else {
                button.classList.remove('active');
            }
        });

        // Set the question in the chat input
        userInput.value = '';
        userInput.placeholder = "Type your answer...";
        userInput.focus();

        // Add the question to the chat
        addBotMessage(question);

        // Auto-speak the question if voice mode is enabled
        if (voiceModeToggle.checked) {
            speakText(question);
        }

        // Update server-side question state
        fetch('/questions/state', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                current_index: index
            })
        }).catch(error => {
            console.error('Error updating question state:', error);
        });
    }

    // Speak text using TTS
    async function speakText(text) {
        return new Promise(async (resolve, reject) => {
            try {
                // No fallback now - only use server TTS
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
                resolve(); // TTS completed successfully

            } catch (error) {
                console.error("Error in speakText:", error);
                showError("TTS failed: " + error.message);
                reject(error);
            }
        });
    }

    // Process TTS queue
    async function processQueue() {
        return new Promise(async (resolve, reject) => {
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
                        resolve(); // Resolve when audio is done playing
                    };

                    // Error handling for audio playback
                    audioElement.onerror = (e) => {
                        console.error("Error playing audio:", e);
                        URL.revokeObjectURL(audioUrl);
                        currentAudioElement = null;
                        reject(new Error("Audio playback failed"));
                    };

                    // Play the audio
                    try {
                        await audioElement.play();
                    } catch (playError) {
                        console.error("Error playing audio:", playError);
                        reject(playError);
                    }

                } else {
                    // Handle JSON response (empty queue or error)
                    const data = await response.json();

                    if (!data.success) {
                        reject(new Error(data.error || 'Failed to process TTS queue'));
                    } else if (data.queue_empty) {
                        console.log("TTS queue is empty");
                        resolve(); // Resolve for empty queue
                    } else {
                        resolve(); // Resolve for other success cases
                    }
                }

            } catch (error) {
                console.error("Error processing TTS queue:", error);
                reject(error);
            }
        });
    }

    // Cancel ongoing TTS
    async function cancelOngoingTts() {
        try {
            console.log("Cancelling ongoing TTS");

            // Cancel browser TTS if active
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }

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

            // Also hide any speaking indicators
            const speakingIndicator = document.getElementById('speaking-indicator');
            if (speakingIndicator) {
                speakingIndicator.style.display = 'none';
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

    // Handle PDF Upload
    async function handlePdfUpload() {
        if (!pdfFileInput.files.length) {
            showError('Please select a PDF file first.');
            return;
        }

        const file = pdfFileInput.files[0];

        // Validate file type
        if (file.type !== 'application/pdf') {
            showError('Only PDF files are allowed.');
            return;
        }

        // Validate file size (10MB max)
        const maxSize = 10 * 1024 * 1024; // 10MB
        if (file.size > maxSize) {
            showError('File size exceeds maximum limit of 10MB.');
            return;
        }

        try {
            // Show upload status
            pdfUploadStatus.style.display = 'block';
            pdfStatusMessage.textContent = 'Uploading PDF...';
            pdfProgressBar.style.width = '0%';
            pdfUploadButton.disabled = true;

            // Create FormData
            const formData = new FormData();
            formData.append('pdf_file', file);

            // Upload with progress tracking
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload-pdf', true);

            // Track progress
            xhr.upload.onprogress = function (e) {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    pdfProgressBar.style.width = percentComplete + '%';
                }
            };

            // Handle response
            xhr.onload = function () {
                if (xhr.status === 200) {
                    const response = JSON.parse(xhr.responseText);

                    // Update PDF status
                    pdfStatusMessage.textContent = 'PDF processed successfully!';
                    pdfProgressBar.style.width = '100%';

                    // Update questions
                    if (response.questions && response.questions.length > 0) {
                        updateQuestions(response.questions);
                        questionSourceIndicator.textContent = `Source: ${response.topic || 'PDF Upload'}`;
                        questionsInfo.textContent = `${response.questions.length} questions generated from your PDF.`;

                        // Add a system message to the chat
                        addBotMessage(response.message || `Generated ${response.questions.length} questions from your PDF.`);
                    }

                    // Reset file input
                    pdfFileInput.value = '';
                } else {
                    // Handle error
                    const response = JSON.parse(xhr.responseText);
                    pdfStatusMessage.textContent = 'Error: ' + (response.error || 'Failed to process PDF');
                    showError(response.error || 'Failed to process PDF');
                }

                // Re-enable upload button
                pdfUploadButton.disabled = false;
            };

            // Handle errors
            xhr.onerror = function () {
                pdfStatusMessage.textContent = 'Network error occurred during upload.';
                showError('Network error occurred during upload.');
                pdfUploadButton.disabled = false;
            };

            // Send the request
            xhr.send(formData);

        } catch (error) {
            console.error('Error uploading PDF:', error);
            pdfStatusMessage.textContent = 'Error: ' + error.message;
            showError('Error uploading PDF: ' + error.message);
            pdfUploadButton.disabled = false;
        }
    }

    // Update difficulty description based on selection
    function updateDifficultyDescription(difficulty) {
        const descriptions = {
            'basic': 'Basic: Focuses on foundational concepts and definitions. Ideal for beginners or initial learning.',
            'intermediate': 'Intermediate: Explores relationships between concepts and applications. Good for reinforcing understanding.',
            'advanced': 'Advanced: Challenges with complex applications and critical thinking. Best for deep mastery.',
            'mixed': 'Mixed: Questions ranging from basic to advanced to provide comprehensive practice.'
        };

        difficultyDescription.textContent = descriptions[difficulty] || descriptions.mixed;
    }

    // Update question controls based on state
    function updateQuestionControls(hasQuestions) {
        nextQuestionButton.disabled = !hasQuestions;
        hintButton.disabled = !hasQuestions;

        if (hasQuestions) {
            nextQuestionButton.style.display = 'block';
            hintButton.style.display = 'block';
        } else {
            nextQuestionButton.style.display = 'none';
            hintButton.style.display = 'none';
        }
    }

    // Update progress display
    function updateProgressDisplay(currentIndex, total, correctCount, incorrectCount) {
        // Update progress count
        progressCount.textContent = `${currentIndex + 1}/${total}`;

        // Update progress bar
        const percentComplete = total > 0 ? ((currentIndex + 1) / total) * 100 : 0;
        progressBar.style.width = `${percentComplete}%`;

        // Update accuracy
        const answeredQuestions = correctCount + incorrectCount;
        const accuracyValue = answeredQuestions > 0 ? (correctCount / answeredQuestions) * 100 : 0;
        accuracyPercent.textContent = `${accuracyValue.toFixed(1)}%`;

        // Update question number
        questionNumber.textContent = `Question ${currentIndex + 1} of ${total}`;
    }

    // Helper function to check if a message is requesting a new topic
    function isNewTopicRequest(message) {
        const patterns = [
            /(?:help me|i want to|i'd like to|can you help me|i need to|let's|let me) (?:review|study|learn|practice|go over|understand)/i,
            /(?:review|study|learn about|practice|quiz me on|test me on)/i,
            /i'm (?:studying|learning|reviewing)/i,
            /(?:questions|quiz|test) (?:about|on|regarding|for|related to)/i
        ];

        return patterns.some(pattern => pattern.test(message));
    }
}; 
