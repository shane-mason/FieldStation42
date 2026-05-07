class StationBump {
    constructor(config = {}) {
        this.container = document.getElementById('bumpContainer');
        this.backgroundLayer = document.getElementById('backgroundLayer');
        this.bgVideoPlayer = document.getElementById('bgVideoPlayer');
        this.contentArea = document.getElementById('contentArea');

        if (this.contentArea) {
            this.contentArea.classList.add('text-hidden');
        }

        this.mainTitle = document.getElementById('mainTitle');
        this.subtitle = document.getElementById('subtitle');
        this.detailLine1 = document.getElementById('detailLine1');
        this.detailLine2 = document.getElementById('detailLine2');
        this.detailLine3 = document.getElementById('detailLine3');
        this.bgMusicPlayer = document.getElementById('bgMusicPlayer');
        this.countdownTimer = document.getElementById('countdownTimer');
        this.countdownDisplay = document.getElementById('countdownDisplay');

        this.videoLoopsRemaining = 1;

        this.config = {
            title: 'FieldStation42',
            subtitle: 'Big Time Watching Is Here!',
            details: ['Transmitting 24/7', 'On FieldStation42', 'It\'s up to you!'],
            backgroundImage: null,
            backgroundVideo: null,
            backgroundVideoLoopCount: 1,
            backgroundVideoAudio: true,
            backgroundColor: '#000000',
            bgColor: null,
            fgColor: null,
            theme: 'dark',
            accentColor: 'white',
            duration: 0,
            nextUp: null,
            variation: 'modern',
            cssOverride: null,
            bgMusic: null,
            loopMusic: true,
            countdown: false,
            textPosition: null,
            textDelay: 0,
            textFadeIn: 0,
            textFadeOut: 0,
            textHideBeforeEnd: 0,
            ...config
        };

        this.init();
    }

    async init() {
        await this.applyConfiguration();
        this.setupTextPresentation();
        this.setupAutoHide();
        this.setupCountdown();
    }

    async applyConfiguration() {
        // Set content
        this.mainTitle.textContent = this.config.title;
        this.subtitle.textContent = this.config.subtitle;

        // Handle nextUp shows or regular details
        if (this.config.nextUp) {
            await this.loadNextUpShows();
        } else {
            // Set regular detail lines
            const detailElements = [this.detailLine1, this.detailLine2, this.detailLine3];
            this.config.details.forEach((detail, index) => {
                if (detailElements[index]) {
                    detailElements[index].textContent = detail;
                    detailElements[index].style.display = detail ? 'block' : 'none';
                }
            });
        }

        // Set background
        if (this.config.backgroundVideo) {
            this.setupBackgroundVideo();
        } else if (this.config.backgroundImage) {
            this.backgroundLayer.style.backgroundImage = `url(${this.config.backgroundImage})`;
            this.container.classList.add('custom-bg');
        } else if (this.config.bgColor) {
            this.container.style.background = this.config.bgColor;
        } else {
            this.container.style.background = this.config.backgroundColor;
        }

        // Apply variation styling
        this.applyVariation();

        // Load custom CSS override if provided
        if (this.config.cssOverride) {
            this.loadCSSOverride();
        }

        // Set custom text colors (overrides variation defaults if provided)
        if (this.config.fgColor) {
            this.mainTitle.style.color = this.config.fgColor;
            this.subtitle.style.color = this.config.fgColor;
            this.detailLine1.style.color = this.config.fgColor;
            this.detailLine2.style.color = this.config.fgColor;
            this.detailLine3.style.color = this.config.fgColor;
        }

        // Handle background music
        this.setupBackgroundMusic();
    }

    applyVariation() {
        // Remove any existing variation classes
        this.container.classList.remove('variation-modern', 'variation-retro', 'variation-corporate', 'variation-terminal');

        // Add the selected variation class
        this.container.classList.add(`variation-${this.config.variation}`);

        // Set default colors based on variation (only if custom colors not provided)
        if (!this.config.bgColor && !this.config.backgroundImage && !this.config.backgroundVideo) {
            const variationDefaults = this.getVariationDefaults();
            if (variationDefaults.bgColor) {
                this.container.style.background = variationDefaults.bgColor;
            }
        }
    }

    getVariationDefaults() {
        const defaults = {
            modern: {
                bgColor: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
                fgColor: null // Uses CSS classes
            },
            retro: {
                bgColor: 'linear-gradient(45deg, #2d1b69 0%, #11052c 50%, #0a0a0a 100%)',
                fgColor: null
            },
            corporate: {
                bgColor: 'linear-gradient(180deg, #f8f9fa 0%, #e9ecef 50%, #dee2e6 100%)',
                fgColor: null
            },
            terminal: {
                bgColor: '#000000',
                fgColor: null
            }
        };

        return defaults[this.config.variation] || defaults.modern;
    }

    loadCSSOverride() {
        // Remove any existing override CSS
        const existingOverride = document.getElementById('css-override');
        if (existingOverride) {
            existingOverride.remove();
        }

        // Create and load new override CSS
        const link = document.createElement('link');
        link.id = 'css-override';
        link.rel = 'stylesheet';
        link.type = 'text/css';
        link.href = this.config.cssOverride;

        // Add error handling
        link.onerror = () => {
            console.warn('Failed to load CSS override:', this.config.cssOverride);
        };

        link.onload = () => {
            console.log('CSS override loaded successfully:', this.config.cssOverride);
        };

        // Append to head to ensure it loads after base styles
        document.head.appendChild(link);
    }

    async loadNextUpShows() {
        try {
            const now = new Date();
            const endTime = new Date(now.getTime() + (4 * 60 * 60 * 1000)); // 4 hours from now

            // Format dates for API (YYYY-MM-DDTHH:MM:SS)
            const formatDateForAPI = (date) => {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                const seconds = String(date.getSeconds()).padStart(2, '0');
                return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
            };

            // Fetch schedule blocks using common.js function
            const scheduleBlocks = await window.fs42Common.fetchSchedule(
                this.config.nextUp,
                formatDateForAPI(now),
                    formatDateForAPI(endTime)
            );

            if (scheduleBlocks && scheduleBlocks.length > 0) {
                const currentShow = scheduleBlocks.find(block => new Date(block.start_time) <= now);
                const upcomingShows = scheduleBlocks.filter(block => new Date(block.start_time) > now);

                // Check if we're within 5 minutes of the current show ending
                let nearEnd = false;
                if (currentShow) {
                    const currentEnd = currentShow.end_time
                    ? new Date(currentShow.end_time)
                    : (upcomingShows.length > 0 ? new Date(upcomingShows[0].start_time) : null);
                    if (currentEnd) {
                        nearEnd = (currentEnd - now) <= (5 * 60 * 1000);
                    }
                }

                const detailElements = [this.detailLine1, this.detailLine2, this.detailLine3];
                let showsToDisplay = [];

                if (currentShow && !nearEnd) {
                    // Show current show labeled "NOW" plus next 2
                    showsToDisplay.push({ label: 'Now', show: currentShow });
                    upcomingShows.slice(0, 2).forEach(show => showsToDisplay.push({ label: null, show }));
                } else {
                    // Near end or no current show: show next 3 upcoming
                    upcomingShows.slice(0, 3).forEach(show => showsToDisplay.push({ label: null, show }));
                }

                showsToDisplay.forEach(({ label, show }, index) => {
                    if (detailElements[index]) {
                        const startTime = new Date(show.start_time);
                        const timeStr = label || startTime.toLocaleTimeString('en-US', {
                            hour: 'numeric',
                            minute: '2-digit',
                            hour12: true
                        });

                        detailElements[index].textContent = `${timeStr} - ${show.title || 'Untitled'}`;
                        detailElements[index].style.display = 'block';
                    }
                });

                // Hide unused detail lines
                for (let i = showsToDisplay.length; i < detailElements.length; i++) {
                    if (detailElements[i]) {
                        detailElements[i].style.display = 'none';
                    }
                }
            } else {
                // No upcoming shows found, show default message
                this.detailLine1.textContent = 'No upcoming shows';
                this.detailLine1.style.display = 'block';
                this.detailLine2.style.display = 'none';
                this.detailLine3.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading next up shows:', error);
            // Fallback to showing error message
            this.detailLine1.textContent = 'Schedule unavailable';
            this.detailLine1.style.display = 'block';
            this.detailLine2.style.display = 'none';
            this.detailLine3.style.display = 'none';
        }
    }

    setupTextPresentation() {
        if (!this.contentArea) return;

        if (this.config.textPosition) {
            this.container.classList.add(`text-position-${this.config.textPosition}`);
        }

        const delayMs = Math.max(parseFloat(this.config.textDelay) || 0, 0) * 1000;
        const fadeInSec = Math.max(parseFloat(this.config.textFadeIn) || 0, 0);

        this.contentArea.style.opacity = '0';
        this.contentArea.style.transition = fadeInSec > 0 ? `opacity ${fadeInSec}s ease-in` : 'none';

        setTimeout(() => {
            this.contentArea.classList.remove('text-hidden');
            this.contentArea.style.opacity = '1';
        }, delayMs);
    }

    setupCountdown() {
        if (!this.config.countdown || this.config.duration <= 0) return;

        this.countdownTimer.style.display = 'block';

        const totalMs = this.config.duration;
        const startTime = Date.now();

        const update = () => {
            const elapsed = Date.now() - startTime;
            const remaining = Math.max(0, totalMs - elapsed);
            const totalSecs = Math.ceil(remaining / 1000);
            const mins = Math.floor(totalSecs / 60);
            const secs = totalSecs % 60;
            this.countdownDisplay.textContent = `${mins}:${String(secs).padStart(2, '0')}`;

            if (remaining > 0) {
                requestAnimationFrame(update);
            }
        };

        requestAnimationFrame(update);
    }

    setupAutoHide() {
        if (this.config.duration > 0) {
            // Enforce minimum duration of 2 seconds (2000ms)
            const adjustedDuration = Math.max(this.config.duration, 2000);

            // Start fade animation 1 second early so total duration matches exactly
            const fadeStartTime = Math.max(adjustedDuration - 1000, 0);

            // Optionally hide the text before the bump itself ends
            if (this.contentArea && this.config.textHideBeforeEnd > 0) {
                const fadeOutSec = Math.max(parseFloat(this.config.textFadeOut) || 0, 0);
                const hideBeforeEndMs = this.config.textHideBeforeEnd * 1000;
                const fadeOutMs = fadeOutSec * 1000;

                const textFadeStartTime = Math.max(
                    adjustedDuration - hideBeforeEndMs - fadeOutMs,
                    0
                );

                setTimeout(() => {
                    this.contentArea.style.transition = fadeOutSec > 0 ? `opacity ${fadeOutSec}s ease-out` : 'none';
                    this.contentArea.style.opacity = '0';
                }, textFadeStartTime);
            }

            setTimeout(() => {
                this.fadeOut();
            }, fadeStartTime);
        }
    }

    fadeOut() {
        if (this.contentArea && this.config.textFadeOut > 0) {
            this.contentArea.style.transition = `opacity ${this.config.textFadeOut}s ease-out`;
            this.contentArea.style.opacity = '0';
        }

        this.container.style.transition = 'opacity 1s ease-out';
        this.container.style.opacity = '0';

        setTimeout(() => {
            this.container.style.display = 'none';
        }, 1000);
    }

    setupBackgroundVideo() {
        if (!this.config.backgroundVideo || !this.bgVideoPlayer) return;

        this.videoLoopsRemaining = Math.max(parseInt(this.config.backgroundVideoLoopCount) || 1, 1);

        this.bgVideoPlayer.src = this.config.backgroundVideo;
        this.bgVideoPlayer.style.display = 'block';
        this.bgVideoPlayer.playsInline = true;
        this.bgVideoPlayer.loop = false;

        // If bg_music is set, keep video audio muted so audio behavior remains predictable.
        // Otherwise, use video audio unless bg_video_audio=false.
        this.bgVideoPlayer.muted = !!this.config.bgMusic || !this.config.backgroundVideoAudio;

        this.container.classList.add('video-bg');

        this.bgVideoPlayer.addEventListener('ended', () => {
            this.videoLoopsRemaining--;

            if (this.videoLoopsRemaining > 0) {
                this.bgVideoPlayer.currentTime = 0;
                this.bgVideoPlayer.play().catch(error => {
                    console.warn('Background video replay failed:', error);
                });
            }
        });

        this.bgVideoPlayer.play().then(() => {
            console.log('Background video started successfully');
        }).catch(error => {
            console.warn('Background video autoplay failed:', error);
        });
    }

    setupBackgroundMusic() {
        if (this.config.bgMusic && this.bgMusicPlayer) {
            this.bgMusicPlayer.src = this.config.bgMusic;
            this.bgMusicPlayer.loop = this.config.loopMusic;
            this.bgMusicPlayer.volume = 0.3; // Set a reasonable default volume

            // Try to play the music
            this.bgMusicPlayer.play().then(() => {
                console.log('Background music started successfully');
            }).catch(error => {
                console.warn('Background music autoplay failed:', error);
                // This is expected in some browsers - the web render system handles autoplay
            });

            // Fade out music when bump fades out
            const originalFadeOut = this.fadeOut.bind(this);
            this.fadeOut = () => {
                this.fadeOutMusic();
                originalFadeOut();
            };
        }
    }

    fadeOutMusic() {
        if (this.bgMusicPlayer && !this.bgMusicPlayer.paused) {
            const fadeInterval = setInterval(() => {
                if (this.bgMusicPlayer.volume > 0.05) {
                    this.bgMusicPlayer.volume = Math.max(0, this.bgMusicPlayer.volume - 0.05);
                } else {
                    this.bgMusicPlayer.pause();
                    this.bgMusicPlayer.volume = 0.3; // Reset for next time
                    clearInterval(fadeInterval);
                }
            }, 50); // Fade over ~1 second
        }
    }

    // Static method to create bump with URL parameters
    static fromURLParams() {
        const params = new URLSearchParams(window.location.search);

        const config = {
            title: params.get('title') || 'FieldStation42',
            subtitle: params.get('subtitle') || 'Its Up to you!',
            details: [
                params.get('detail1') || 'Big time watching is here!',
                params.get('detail2') || 'Broadcasting 24/7',
                params.get('detail3') || 'Sweet.'
            ].filter(Boolean),
            backgroundImage: params.get('bg') || null,
            backgroundVideo: params.get('bg_video') || null,
            backgroundVideoLoopCount: parseInt(params.get('bg_video_loop_count')) || 1,
            backgroundVideoAudio: params.get('bg_video_audio') !== 'false',
            backgroundColor: params.get('bgcolor') || '#000000',
            bgColor: params.get('bg_color') || null,
            fgColor: params.get('fg_color') || null,
            theme: params.get('theme') || 'dark',
            accentColor: params.get('accent') || 'white',
            duration: parseInt(params.get('duration')) || 0,
            nextUp: params.get('next_network') || null,
            variation: params.get('variation') || 'modern',
            cssOverride: params.get('css') || null,
            bgMusic: params.get('bg_music') || null,
            loopMusic: params.get('loopmusic') !== 'false',
            countdown: params.get('countdown') === 'true',
            textPosition: params.get('text_position') || null,
            textDelay: parseFloat(params.get('text_delay')) || 0,
            textFadeIn: parseFloat(params.get('text_fade_in')) || 0,
            textFadeOut: parseFloat(params.get('text_fade_out')) || 0,
            textHideBeforeEnd: parseFloat(params.get('text_hide_before_end')) || 0
        };

        return new StationBump(config);
    }

    // Method to update content dynamically
    async updateContent(newConfig) {
        Object.assign(this.config, newConfig);
        await this.applyConfiguration();
        this.setupTextPresentation();
    }
}

// API for external control
window.StationBump = StationBump;

// Global configuration function
window.configureBump = async function(config) {
    if (window.currentBump) {
        await window.currentBump.updateContent(config);
    } else {
        window.currentBump = new StationBump(config);
    }
};

// Initialize bump on page load
document.addEventListener('DOMContentLoaded', () => {
    // Check if URL parameters are provided
    const hasParams = window.location.search.length > 0;

    if (hasParams) {
        window.currentBump = StationBump.fromURLParams();
    } else {
        // Default configuration for FieldStation42
        window.currentBump = new StationBump();
    }
});

// Example usage in console:
// configureBump({
//     title: 'RETRO FM',
//     subtitle: 'Classic Hits Radio',
//     details: ['98.5 FM', 'Your Music Station', 'retrofm.com'],
//     accentColor: 'blue',
//     backgroundImage: 'background.jpg'
// });
