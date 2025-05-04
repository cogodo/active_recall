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

    // Audio recording variables
    let mediaRecorder = null;
    let audioChunks = [];
    let audioContext = null;
    let analyser = null;
    let microphone = null;
    let isRecording = false;
    let recordingInterval = null;

    // Speech synthesis and audio recording variables
    let isListening = false;
    let continuousListening = false;
    let autoRead = false;

    // Cartesia variables
    let cartesiaClient = null;
    let cartesiaWebsocket = null;
    let cartesiaWebPlayer = null;
    let currentContextId = null;
    let currentAbortController = null;
    let isSpeaking = false;

    // Initialize Cartesia client
    async function initializeCartesia() {
        if (cartesiaClient) {
            return cartesiaClient;
        }

        try {
            console.log("Initializing Cartesia client...");
            // Get API key from server
            const response = await fetch('/get-cartesia-key');
            console.log("Received response from /get-cartesia-key");
            const data = await response.json();
            console.log("Parsed response:", data);

            if (!data.available) {
                console.warn("Cartesia API key not available:", data.message);
                return null;
            }

            console.log("Cartesia API key received");

            // Initialize the SDK client properly
            cartesiaClient = new Cartesia.Client({
                apiKey: data.key,
                cartesiaVersion: "2025-04-16",
                maxRetries: 2,
                timeoutInSeconds: 30
            });

            // Initialize WebPlayer for browser audio playback
            if (Cartesia.WebPlayer) {
                try {
                    cartesiaWebPlayer = new Cartesia.WebPlayer();
                    console.log("Cartesia WebPlayer initialized");
                } catch (e) {
                    console.error("Failed to initialize WebPlayer:", e);
                    throw new Error("WebPlayer initialization failed. Text-to-speech won't work.");
                }
            } else {
                console.error("Cartesia WebPlayer not available in SDK");
                throw new Error("WebPlayer not available in Cartesia SDK. Text-to-speech won't work.");
            }

            console.log("Cartesia client initialized successfully");
            return cartesiaClient;
        } catch (error) {
            console.error("Failed to initialize Cartesia client:", error);
            return null;
        }
    }

    // Cancel any ongoing TTS
    function cancelOngoingTts() {
        console.log("Cancelling any ongoing TTS...");

        // Set flag to stop processing
        isSpeaking = false;

        // Abort any in-progress requests
        if (currentAbortController) {
            try {
                currentAbortController.abort();
                console.log("Aborted ongoing TTS request");
            } catch (e) {
                console.error("Error aborting TTS request:", e);
            }
            currentAbortController = null;
        }

        // Hide speaking indicator if visible
        let speakingIndicator = document.getElementById('speaking-indicator');
        if (speakingIndicator) {
            speakingIndicator.style.display = 'none';
        }

        // Clean up WebSocket if it exists
        if (cartesiaWebsocket) {
            try {
                cartesiaWebsocket.close();
                console.log("Closed WebSocket connection");
            } catch (e) {
                console.error("Error closing WebSocket:", e);
            }
            cartesiaWebsocket = null;
        }

        // Stop WebPlayer if active
        if (cartesiaWebPlayer && typeof cartesiaWebPlayer.stop === 'function') {
            try {
                cartesiaWebPlayer.stop();
                console.log("Stopped WebPlayer");
            } catch (e) {
                console.error("Error stopping WebPlayer:", e);
            }
        }

        // Reset context ID
        currentContextId = null;

        console.log("TTS cancelled successfully");
    }

    // Function to convert text to speech using Cartesia
    async function speakText(text) {
        try {
            console.log("Starting text-to-speech process for:", text.substring(0, 50) + "...");

            // Cancel any ongoing TTS
            cancelOngoingTts();

            // Show speaking indicator
            let speakingIndicator = document.getElementById('speaking-indicator');
            if (!speakingIndicator) {
                speakingIndicator = document.createElement('div');
                speakingIndicator.id = 'speaking-indicator';
                speakingIndicator.className = 'speaking-indicator';
                speakingIndicator.textContent = 'Assistant is speaking...';
                document.body.appendChild(speakingIndicator);
            }
            speakingIndicator.style.display = 'block';

            // Get Cartesia client
            const client = await initializeCartesia();
            console.log("Cartesia client ready:", !!client);

            // Verify we have a proper Cartesia client with WebPlayer
            if (!client || !cartesiaWebPlayer) {
                throw new Error("Cartesia client or WebPlayer not available");
            }

            // Get voice and model config
            const { voice: voiceConfig, model: modelId } = getVoiceConfig();
            console.log(`Using voice: `, voiceConfig);
            console.log(`Using model: ${modelId}`);

            // Generate context ID to identify this session
            currentContextId = `ctx_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
            console.log(`Generated context ID: ${currentContextId}`);
            isSpeaking = true;

            // Create a new abort controller for this request
            currentAbortController = new AbortController();

            // For longer texts, use WebSocket streaming with contexts
            const shouldStream = text.length > 100;

            if (shouldStream) {
                console.log("Using WebSocket streaming for longer text");

                try {
                    // Initialize WebSocket if not already done
                    if (!cartesiaWebsocket) {
                        console.log("Creating new Cartesia WebSocket");
                        cartesiaWebsocket = client.tts.websocket({
                            container: "raw",
                            encoding: "pcm_f32le",
                            sampleRate: 24000
                        });

                        // Connect to WebSocket
                        await cartesiaWebsocket.connect();
                        console.log("WebSocket connected successfully");
                    }

                    // Split text into sentences for streaming
                    const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
                    console.log(`Splitting text into ${sentences.length} parts for streaming`);

                    // Prepare voice parameter
                    const voiceParam = typeof voiceConfig === 'string'
                        ? { mode: "id", id: voiceConfig }
                        : voiceConfig;

                    // Send initial request with first sentence
                    console.log(`Sending first sentence: "${sentences[0].substring(0, 30)}..."`);
                    const response = await cartesiaWebsocket.send({
                        contextId: currentContextId,
                        modelId: modelId,
                        voice: voiceParam,
                        transcript: sentences[0],
                        language: "en",
                    }, {
                        abortSignal: currentAbortController.signal
                    });

                    // Register message handler for logging
                    response.on("message", (message) => {
                        console.log(`Received WebSocket message type: ${message.type}`);
                    });

                    // Handle response errors
                    response.on("error", (error) => {
                        console.error("Error in TTS response:", error);
                        throw error;
                    });

                    // Play the audio with WebPlayer
                    await cartesiaWebPlayer.play(response.source);

                    // If there are more sentences, continue with them
                    if (sentences.length > 1 && isSpeaking) {
                        for (let i = 1; i < sentences.length; i++) {
                            if (!isSpeaking) {
                                console.log("TTS cancelled, stopping sentence processing");
                                break;
                            }

                            const sentence = sentences[i].trim();
                            if (sentence.length === 0) continue;

                            console.log(`Sending continuation sentence ${i}/${sentences.length}: "${sentence.substring(0, 30)}..."`);

                            // Send continuation request
                            await cartesiaWebsocket.continue({
                                contextId: currentContextId,
                                transcript: sentence
                            }, {
                                abortSignal: currentAbortController.signal
                            });

                            // Wait for processing
                            await new Promise(resolve => setTimeout(resolve, 200));
                        }
                    }
                } catch (streamError) {
                    if (streamError.name === 'AbortError') {
                        console.log("TTS request was aborted");
                    } else {
                        console.error("Error processing TTS stream:", streamError);
                        throw streamError;
                    }
                }
            } else {
                // For short text, use WebPlayer with bytes API
                console.log("Using bytes API with WebPlayer for shorter text");

                try {
                    // Create the TTS request
                    const ttsRequest = {
                        modelId: modelId,
                        transcript: text,
                        language: "en",
                        outputFormat: {
                            container: "raw",
                            encoding: "pcm_f32le",
                            sampleRate: 24000
                        }
                    };

                    // Add voice configuration
                    if (typeof voiceConfig === 'string') {
                        ttsRequest.voiceId = voiceConfig;
                    } else {
                        ttsRequest.voice = voiceConfig;
                    }

                    console.log("Sending TTS request:", ttsRequest);

                    // Get the audio bytes
                    const audioBytes = await client.tts.bytes(ttsRequest, {
                        abortSignal: currentAbortController.signal
                    });
                    console.log("Received audio data from bytes API");

                    // Create a source from the bytes
                    const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });

                    if (cartesiaWebPlayer) {
                        // Create a source from the bytes and play with WebPlayer
                        const audioSource = await Cartesia.createSourceFromBlob(audioBlob);
                        await cartesiaWebPlayer.play(audioSource);
                    } else {
                        // Fallback to standard Audio element
                        const audioUrl = URL.createObjectURL(audioBlob);
                        const audio = new Audio(audioUrl);

                        audio.onerror = (e) => {
                            console.error("Audio playback error:", e);
                            URL.revokeObjectURL(audioUrl);
                            throw new Error(`Audio playback error: ${e.message || 'Unknown error'}`);
                        };

                        // Set event handlers before playing
                        audio.onended = () => {
                            console.log("Audio playback completed");
                            URL.revokeObjectURL(audioUrl);
                        };

                        console.log("Starting audio playback with regular Audio element");
                        await audio.play();
                    }
                } catch (bytesError) {
                    if (bytesError.name === 'AbortError') {
                        console.log("TTS request was aborted");
                    } else {
                        console.error("Error with bytes TTS API:", bytesError);
                        throw bytesError;
                    }
                }
            }

            console.log("TTS process completed successfully");

            // Clean up when done if still speaking
            if (isSpeaking) {
                // Don't cancel entirely, just reset flags
                isSpeaking = false;
                currentAbortController = null;

                // Resume recording if in continuous mode
                if (continuousListening && !isRecording) {
                    setTimeout(() => {
                        startRecording();
                    }, 500);
                }
            }

        } catch (error) {
            // Check for Cartesia error
            if (error instanceof Cartesia?.CartesiaError) {
                console.error(`Cartesia API error (${error.statusCode}): ${error.message}`);
                errorMessage.textContent = `TTS error (${error.statusCode}): ${error.message}`;
            } else {
                console.error("Error in speakText:", error);
                errorMessage.textContent = 'Text-to-speech error: ' + error.message;
            }

            // Try server fallback if SDK failed
            try {
                console.error("Attempting server fallback for TTS...");
                await serverTtsPlayback(text);
            } catch (fallbackError) {
                console.error("Server fallback also failed:", fallbackError);

                errorMessage.style.display = 'block';
                setTimeout(() => {
                    errorMessage.style.display = 'none';
                }, 5000);

                // Clean up
                cancelOngoingTts();
            }

            // Resume recording if in continuous mode
            if (continuousListening && !isRecording) {
                setTimeout(() => {
                    startRecording();
                }, 500);
            }
        }
    }

    // Server fallback for TTS when SDK fails
    async function serverTtsPlayback(text) {
        // First test if the endpoint is available
        console.log("Testing TTS endpoint availability...");
        const testResponse = await fetch('/test-tts');
        const testData = await testResponse.json();
        console.log("TTS test response:", testData);

        if (!testResponse.ok) {
            throw new Error(`Server TTS test failed with status: ${testResponse.status}`);
        }

        console.log("TTS endpoint test successful, proceeding with actual request");

        // Now make the actual TTS request
        const response = await fetch('/text-to-speech', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ text, voice: "nova" }),
        });

        console.log("Server TTS response status:", response.status);

        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
            } catch (e) {
                // If it's not valid JSON, get the text
                const errorText = await response.text();
                throw new Error(`Server TTS error (${response.status}): ${errorText.substring(0, 100)}`);
            }
            throw new Error(`Server TTS error: ${errorData.error || 'Unknown error'}`);
        }

        // Get the binary audio data
        const audioBlob = await response.blob();
        console.log("Received audio blob:", audioBlob.size, "bytes, type:", audioBlob.type);

        // Create an audio element and play it
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);

        audio.onerror = (e) => {
            console.error("Audio playback error:", e);
            URL.revokeObjectURL(audioUrl);
            throw new Error(`Audio playback error: ${e.message || 'Unknown error'}`);
        };

        // Set event handlers before playing
        audio.onended = () => {
            console.log("Audio playback completed");
            URL.revokeObjectURL(audioUrl);
            cancelOngoingTts();

            // Resume recording if in continuous mode
            if (continuousListening && !isRecording) {
                setTimeout(() => {
                    startRecording();
                }, 500);
            }
        };

        console.log("Starting audio playback");
        const playPromise = audio.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.error("Audio play promise error:", error);
                URL.revokeObjectURL(audioUrl);
            });
        }
    }

    // Initialize immediately
    initializeCartesia();

    // Add initial bot message
    addBotMessage("Hi! I'm your Active Recall Study Assistant. Tell me what topic you'd like to review today, and I'll help you practice with targeted questions.");

    // Initialize audio recording for Whisper
    initializeSpeechRecognition();

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
        autoRead = this.checked;
    });

    // Clean up audio resources on page unload
    window.addEventListener('beforeunload', function () {
        stopRecording();
        cancelOngoingTts();

        if (audioContext) {
            audioContext.close().catch(e => console.error("Error closing audio context:", e));
        }
    });

    // Initialize audio context for visualizer
    function initializeAudioContext() {
        console.log("Initializing audio context");
        try {
            // AudioContext must be created or resumed after a user gesture
            if (!audioContext) {
                console.log("Creating new AudioContext");
                audioContext = new (window.AudioContext || window.webkitAudioContext)();

                // Chrome and other browsers require user gesture to start audio context
                if (audioContext.state === 'suspended') {
                    console.log("AudioContext suspended, attempting to resume");
                    audioContext.resume().then(() => {
                        console.log("AudioContext resumed successfully");
                    }).catch(err => {
                        console.error("Failed to resume AudioContext:", err);
                    });
                }
            } else {
                // Ensure the context is resumed if it was suspended
                if (audioContext.state === 'suspended') {
                    console.log("Existing AudioContext suspended, attempting to resume");
                    audioContext.resume().then(() => {
                        console.log("AudioContext resumed successfully");
                    }).catch(err => {
                        console.error("Failed to resume AudioContext:", err);
                    });
                }
            }

            if (!analyser) {
                console.log("Creating audio analyser");
                analyser = audioContext.createAnalyser();
                analyser.fftSize = 256;
            }

            return true;
        } catch (e) {
            console.error("Error initializing audio context:", e);
            errorMessage.textContent = `Audio initialization error: ${e.message}`;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 3000);
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
            // Create variation so not all bars are the same height
            const variation = 0.4 + Math.sin(index * 0.2) * 0.2;
            const value = average * variation;
            // Set a minimum height for visual appeal
            const height = Math.max(3, Math.min(40, value * 0.4));
            bar.style.height = `${height}px`;
        });
    }

    // Start recording audio with visualization
    async function startRecording() {
        try {
            console.log("Starting recording process");
            if (!initializeAudioContext()) {
                console.error("Failed to initialize audio context");
                return;
            }

            console.log("Requesting getUserMedia for high-quality audio");
            // Get high-quality audio stream optimized for speech
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 48000,
                    channelCount: 1 // Mono for speech
                }
            }).catch(error => {
                console.error("getUserMedia error:", error.name, error.message);
                errorMessage.textContent = `Microphone access error: ${error.message}`;
                errorMessage.style.display = 'block';
                setTimeout(() => {
                    errorMessage.style.display = 'none';
                }, 5000);
                throw error; // Re-throw to be caught by the outer catch
            });

            console.log("Audio stream obtained successfully");

            // Store stream for later cleanup
            window.currentAudioStream = stream;

            // Connect to visualizer
            microphone = audioContext.createMediaStreamSource(stream);
            microphone.connect(analyser);
            console.log("Connected to audio analyzer");

            // Try different formats in order of preference
            let mediaRecorderOptions;

            // Test supported formats - different browsers support different formats
            const mimeTypes = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/ogg;codecs=opus',
                'audio/mp4;codecs=opus'
            ];

            // Find first supported type
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

            // Create recorder with selected options or default
            try {
                if (mediaRecorderOptions) {
                    mediaRecorder = new MediaRecorder(stream, mediaRecorderOptions);
                } else {
                    // Fallback to default format
                    console.warn("None of the preferred audio formats are supported, using default");
                    mediaRecorder = new MediaRecorder(stream);
                }
            } catch (e) {
                console.warn("Error creating MediaRecorder with options, using default", e);
                mediaRecorder = new MediaRecorder(stream);
            }

            audioChunks = [];

            // Handle data available event
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                    console.log(`Audio chunk added: ${event.data.size} bytes`);
                }
            };

            // Handle recording stop event
            mediaRecorder.onstop = async () => {
                console.log(`Recording stopped, collected ${audioChunks.length} chunks`);
                // Process recording only if in continuous mode
                if (continuousListening) {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    console.log(`Created audio blob of size: ${audioBlob.size} bytes`);
                    await processAudioWithWhisper(audioBlob);

                    // Start a new recording after processing if still in continuous mode
                    if (continuousListening) {
                        console.log("Restarting recording");
                        startRecording();
                    }
                }

                // Clean up
                if (microphone) {
                    microphone.disconnect();
                    microphone = null;
                }

                // Reset visualization
                visualizerBarElements.forEach(bar => {
                    bar.style.height = '3px';
                });

                // Hide visualizer if not in continuous mode
                if (!continuousListening) {
                    audioVisualizer.style.display = 'none';
                }
            };

            // Start recording and request data every 1 second to ensure we capture chunks
            mediaRecorder.start(1000);
            console.log("MediaRecorder started");
            isRecording = true;

            // Show visualizer
            audioVisualizer.style.display = 'block';

            // Start visualizer updates
            if (recordingInterval) clearInterval(recordingInterval);
            recordingInterval = setInterval(updateVisualizer, 100);

            // In continuous mode, automatically stop and restart recording every 10 seconds
            if (continuousListening) {
                setTimeout(() => {
                    if (isRecording && mediaRecorder && mediaRecorder.state === 'recording') {
                        console.log("Stopping recording after timeout");
                        mediaRecorder.stop();
                        isRecording = false;
                    }
                }, 10000); // 10 seconds for better Whisper performance
            }

            return true;
        } catch (error) {
            console.error('Error starting recording:', error);

            // Give specific error messages based on the error type
            if (error.name === 'NotAllowedError') {
                errorMessage.textContent = 'Microphone access denied. Please allow microphone access in your browser settings.';
            } else if (error.name === 'NotFoundError') {
                errorMessage.textContent = 'No microphone found. Please connect a microphone and try again.';
            } else if (error.name === 'NotReadableError') {
                errorMessage.textContent = 'Microphone is already in use by another application.';
            } else {
                errorMessage.textContent = 'Error accessing microphone: ' + error.message;
            }

            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);

            // Reset UI state
            continuousListening = false;
            isListening = false;
            micButton.classList.remove('listening');
            micButton.classList.remove('continuous');
            listeningIndicator.style.display = 'none';
            continuousIndicator.style.display = 'none';

            return false;
        }
    }

    // Stop recording audio
    function stopRecording() {
        if (mediaRecorder && isRecording) {
            try {
                if (mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                }
                isRecording = false;

                if (recordingInterval) {
                    clearInterval(recordingInterval);
                    recordingInterval = null;
                }

                // Stop all audio tracks
                if (window.currentAudioStream) {
                    window.currentAudioStream.getTracks().forEach(track => track.stop());
                }
            } catch (error) {
                console.error('Error stopping recording:', error);
            }
        }
    }

    // Process audio with OpenAI Whisper
    async function processAudioWithWhisper(audioBlob) {
        try {
            console.log("Processing audio with Whisper, blob size:", audioBlob.size);

            // Create FormData object for direct file upload
            const formData = new FormData();
            formData.append('audio_file', audioBlob, 'recording.webm');

            // Call server with audio file
            console.log("Sending audio file to /transcribe endpoint");
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData // No need for Content-Type header, browser sets it automatically with boundary
            });

            const data = await response.json();
            console.log("Transcription response:", data);

            if (!data.success) {
                throw new Error(data.error || 'Transcription failed');
            }

            // If we got a valid transcription with content, process it
            if (data.text && data.text.trim()) {
                console.log("Transcription received:", data.text.trim());
                userInput.value = data.text.trim();
                processVoiceInput(data.text.trim());
            } else {
                console.log("No transcription text received");
            }

            return data.text;
        } catch (error) {
            console.error('Error in processAudioWithWhisper:', error);
            errorMessage.textContent = 'Error with speech recognition: ' + error.message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 3000);
            throw error;
        }
    }

    // Function to toggle Whisper voice recording
    function toggleSpeechRecognition() {
        console.log("Toggling speech recognition. Current state:", isListening);

        if (isListening) {
            // Stop listening
            continuousListening = false;
            isListening = false;
            stopRecording();
            micButton.classList.remove('listening');
            micButton.classList.remove('continuous');
            listeningIndicator.style.display = 'none';
            continuousIndicator.style.display = 'none';
            audioVisualizer.style.display = 'none';
        } else {
            // Show permission request indicator
            micButton.classList.add('requesting');
            micButton.innerHTML = '<i>⏳</i>';  // Hour glass icon
            errorMessage.textContent = 'Requesting microphone access...';
            errorMessage.style.display = 'block';

            // First ensure we have microphone permission
            console.log("Requesting microphone access...");
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(stream => {
                    // Stop the test stream
                    stream.getTracks().forEach(track => track.stop());

                    // Reset permission indicator
                    micButton.classList.remove('requesting');
                    micButton.innerHTML = '<i>🎤</i>';
                    errorMessage.style.display = 'none';

                    // Start listening
                    continuousListening = true;
                    isListening = true;
                    micButton.classList.add('listening');
                    micButton.classList.add('continuous');
                    listeningIndicator.style.display = 'inline';
                    continuousIndicator.style.display = 'block';

                    // Start recording
                    startRecording();
                })
                .catch(err => {
                    // Reset permission indicator
                    micButton.classList.remove('requesting');
                    micButton.innerHTML = '<i>🎤</i>';

                    console.error("Microphone access error:", err);
                    errorMessage.textContent = `Microphone access denied: ${err.message}`;
                    errorMessage.style.display = 'block';
                    setTimeout(() => {
                        errorMessage.style.display = 'none';
                    }, 5000);
                });
        }
    }

    // Process voice input after debouncing
    function processVoiceInput(transcript) {
        if (!transcript.trim()) return;

        // Check for voice commands
        const lowerTranscript = transcript.toLowerCase();

        // Handle specific voice commands with natural language patterns
        if (lowerTranscript.match(/^(next|next question|show next|try next|give me the next)(\s|$)/)) {
            // Find and click the next question button if available
            const nextButton = document.querySelector('.ask-question-button');
            if (nextButton) {
                nextButton.click();
                return;
            }
        } else if (lowerTranscript.match(/^(repeat|say again|what did you say|can you repeat that)(\s|$)/)) {
            // Repeat the last bot message
            const botMessages = document.querySelectorAll('.bot-message');
            if (botMessages.length > 0) {
                const lastMessage = botMessages[botMessages.length - 1].textContent;
                speakText(lastMessage);
                return;
            }
        } else if (lowerTranscript.match(/^(stop listening|turn off voice|exit voice|end voice)(\s|$)/)) {
            // Stop continuous listening
            continuousListening = false;
            isListening = false;
            stopRecording();
            micButton.classList.remove('listening');
            micButton.classList.remove('continuous');
            listeningIndicator.style.display = 'none';
            continuousIndicator.style.display = 'none';
            audioVisualizer.style.display = 'none';
            return;
        } else if (lowerTranscript.match(/^(clear|clear chat|start over|start fresh|reset|reset chat)(\s|$)/)) {
            // Clear the chat history visually (server session remains)
            chatMessages.innerHTML = '';
            addBotMessage("Chat cleared. What would you like to discuss now?");
            return;
        }

        // For all other input, send as a message to the server
        userInput.value = transcript;
        sendMessage();
    }

    function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        // Add user message to chat
        addUserMessage(message);
        userInput.value = '';

        // Show typing indicator
        typingIndicator.style.display = 'block';
        errorMessage.style.display = 'none';

        // Temporarily pause voice recording during API call to avoid capturing feedback
        const wasListening = isListening;
        if (wasListening && isRecording) {
            try {
                // Just pause, don't fully stop continuous mode
                stopRecording();
            } catch (e) {
                console.error("Error pausing recording:", e);
            }
        }

        // Send to server
        fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        })
            .then(response => response.json())
            .then(data => {
                // Hide typing indicator
                typingIndicator.style.display = 'none';

                if (data.error) {
                    errorMessage.textContent = data.error;
                    errorMessage.style.display = 'block';
                    return;
                }

                // Add bot response
                addBotMessage(data.response);

                // Speak the response if auto-read is enabled
                if (autoRead) {
                    speakText(data.response);
                }

                // Update questions if provided
                if (data.questions && data.questions.length > 0) {
                    updateQuestions(data.questions);
                }

                // Resume voice recording if it was active before
                if (wasListening && continuousListening && !isRecording) {
                    // Small delay to ensure speech synthesis and recording don't conflict
                    setTimeout(() => {
                        try {
                            startRecording();
                        } catch (e) {
                            console.error("Error resuming recording:", e);
                        }
                    }, 1000);
                }
            })
            .catch(error => {
                typingIndicator.style.display = 'none';
                errorMessage.textContent = 'An error occurred. Please try again.';
                errorMessage.style.display = 'block';
                console.error('Error:', error);

                // Resume voice recording even on error
                if (wasListening && continuousListening && !isRecording) {
                    setTimeout(() => {
                        try {
                            startRecording();
                        } catch (e) {
                            console.error("Error resuming recording:", e);
                        }
                    }, 1000);
                }
            });
    }

    function addUserMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user-message';
        messageDiv.textContent = text;
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

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
        listenButton.title = 'Listen with Cartesia TTS';
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
            listenButton.title = 'Listen with Cartesia TTS';
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
                askQuestion(question);
            });

            questionsList.appendChild(questionDiv);
        });
    }

    function askQuestion(question) {
        // Find the question index
        const questionElements = document.querySelectorAll('.question');
        let questionIndex = 0;

        for (let i = 0; i < questionElements.length; i++) {
            if (questionElements[i].textContent.includes(question)) {
                questionIndex = i;
                break;
            }
        }

        // Add a button for the bot to ask this specific question
        const askButton = document.createElement('button');
        askButton.className = 'ask-question-button';
        askButton.textContent = 'Next Question';
        askButton.setAttribute('data-index', questionIndex);

        askButton.addEventListener('click', function () {
            // Remove this button after clicking
            this.remove();

            // Get the question index
            const index = parseInt(this.getAttribute('data-index')) + 1;

            // Send the request to get the next question
            fetch('/next-question', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ question_index: index })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        errorMessage.textContent = data.error;
                        errorMessage.style.display = 'block';
                        return;
                    }

                    // Display the next question
                    const nextQuestionText = `Let's try this question: ${data.question}`;
                    addBotMessage(nextQuestionText);

                    // Speak the question if auto-read is enabled
                    if (autoRead) {
                        speakText(data.question);
                    }

                    // Focus on the input field for the user to answer
                    userInput.focus();
                })
                .catch(error => {
                    errorMessage.textContent = 'An error occurred. Please try again.';
                    errorMessage.style.display = 'block';
                    console.error('Error:', error);
                });
        });

        // Add button to the chat
        chatMessages.appendChild(askButton);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Helper function to get voice configuration
    function getVoiceConfig() {
        // Use only nova voice with sonic-2 model as requested
        const voiceConfig = "nova";  // Simple string format
        const modelId = "sonic-2";

        console.log("Using fixed voice configuration: nova");
        console.log("Using fixed model: sonic-2");

        return { voice: voiceConfig, model: modelId };
    }
} 