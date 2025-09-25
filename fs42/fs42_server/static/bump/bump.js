class StationBump {
    constructor(config = {}) {
        this.container = document.getElementById('bumpContainer');
        this.backgroundLayer = document.getElementById('backgroundLayer');
        this.mainTitle = document.getElementById('mainTitle');
        this.subtitle = document.getElementById('subtitle');
        this.detailLine1 = document.getElementById('detailLine1');
        this.detailLine2 = document.getElementById('detailLine2');
        this.detailLine3 = document.getElementById('detailLine3');
        this.bgMusicPlayer = document.getElementById('bgMusicPlayer');
        
        this.config = {
            title: 'FieldStation42',
            subtitle: 'Big Time Watching Is Here!',
            details: ['Transmitting 24/7', 'On FieldStation42', 'It\'s up to you!'],
            backgroundImage: null,
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
            ...config
        };
        
        this.init();
    }
    
    async init() {
        await this.applyConfiguration();
        this.setupAutoHide();
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
        if (this.config.backgroundImage) {
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
        if (!this.config.bgColor && !this.config.backgroundImage) {
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
                // Filter to upcoming shows (not currently airing)
                const upcomingShows = scheduleBlocks.filter(block => {
                    const blockStart = new Date(block.start_time);
                    return blockStart > now;
                }).slice(0, 3); // Take first 3 upcoming shows
                
                const detailElements = [this.detailLine1, this.detailLine2, this.detailLine3];
                
                upcomingShows.forEach((show, index) => {
                    if (detailElements[index]) {
                        const startTime = new Date(show.start_time);
                        const timeStr = startTime.toLocaleTimeString('en-US', { 
                            hour: 'numeric', 
                            minute: '2-digit',
                            hour12: true
                        });
                        
                        detailElements[index].textContent = `${timeStr} - ${show.title || 'Untitled'}`;
                        detailElements[index].style.display = 'block';
                    }
                });
                
                // Hide unused detail lines
                for (let i = upcomingShows.length; i < detailElements.length; i++) {
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
    
    setupAutoHide() {
        if (this.config.duration > 0) {
            // Enforce minimum duration of 2 seconds (2000ms)
            const adjustedDuration = Math.max(this.config.duration, 2000);
            
            // Start fade animation 1 second early so total duration matches exactly
            const fadeStartTime = Math.max(adjustedDuration - 1000, 0);
            
            setTimeout(() => {
                this.fadeOut();
            }, fadeStartTime);
        }
    }
    
    fadeOut() {
        this.container.style.transition = 'opacity 1s ease-out';
        this.container.style.opacity = '0';
        
        setTimeout(() => {
            this.container.style.display = 'none';
        }, 1000);
    }

    setupBackgroundMusic() {
        if (this.config.bgMusic && this.bgMusicPlayer) {
            this.bgMusicPlayer.src = this.config.bgMusic;
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
            backgroundColor: params.get('bgcolor') || '#000000',
            bgColor: params.get('bg_color') || null,
            fgColor: params.get('fg_color') || null,
            theme: params.get('theme') || 'dark',
            accentColor: params.get('accent') || 'white',
            duration: parseInt(params.get('duration')) || 0,
            nextUp: params.get('next_network') || null,
            variation: params.get('variation') || 'modern',
            cssOverride: params.get('css') || null,
            bgMusic: params.get('bg_music') || null
        };
        
        return new StationBump(config);
    }
    
    // Method to update content dynamically
    async updateContent(newConfig) {
        Object.assign(this.config, newConfig);
        await this.applyConfiguration();
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