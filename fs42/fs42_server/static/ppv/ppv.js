class PPVViewer {
    constructor(config = {}) {
        // Container elements
        this.container = document.getElementById('ppvContainer');
        this.backgroundLayer = document.getElementById('backgroundLayer');
        this.loadingOverlay = document.getElementById('loadingOverlay');

        // Display elements
        this.currentImage = document.getElementById('currentImage');
        this.noImage = document.getElementById('noImage');
        this.contentTitle = document.getElementById('contentTitle');
        this.contentDetails = document.getElementById('contentDetails');
        this.contentDescription = document.getElementById('contentDescription');
        this.slideCounter = document.getElementById('slideCounter');

        this.config = {
            channelNumber: null,
            variation: 'modern',
            cssOverride: null,
            backgroundImage: null,
            bgColor: null,
            slideDuration: 10000, // 10 seconds per slide
            ...config
        };

        this.contents = [];
        this.currentIndex = 0;
        this.slideshowTimer = null;
        this.slideDirection = 'up'; // Track slide direction: 'up' or 'down'

        // Music playlist
        this.bgMusicPlayer = document.getElementById('bgMusicPlayer');
        this.musicPlaylist = [];
        this.currentMusicIndex = 0;

        this.init();
    }

    async init() {
        await this.loadContent();
        await this.loadMusicPlaylist();
        this.setupKeyboardNavigation();
        this.applyConfiguration();
        this.setupBackgroundMusic();
        this.startSlideshow();
    }

    async loadContent() {
        if (!this.config.channelNumber) {
            this.showError('No channel number specified');
            return;
        }

        try {
            // Build API URL
            let apiUrl = `ppv/${this.config.channelNumber}`;
            if (this.config.variation && this.config.variation !== 'modern') {
                apiUrl += `?variation=${encodeURIComponent(this.config.variation)}`;
            }

            const response = await window.fs42Api.get(apiUrl);

            // Store contents
            this.contents = response.contents || [];

            // Hide loading overlay
            this.loadingOverlay.classList.add('hidden');

            // Show first slide
            if (this.contents.length > 0) {
                this.showSlide(0);
            } else {
                this.showError('No content available');
            }
        } catch (error) {
            console.error('Error loading PPV content:', error);
            this.showError(`Failed to load content: ${error.message || 'Unknown error'}`);
        }
    }

    showSlide(index) {
        if (index < 0 || index >= this.contents.length) return;

        this.currentIndex = index;
        const content = this.contents[index];

        // Update slide counter
        this.slideCounter.textContent = `${index + 1}/${this.contents.length}`;

        // Update text content
        this.contentTitle.textContent = content.nfo?.title || content.filename;
        this.contentDetails.textContent = content.nfo?.info || '';
        this.contentDescription.textContent = content.nfo?.description || '';

        // Update image with vertical slide effect
        if (content.has_image && content.image_url) {
            // Slide out current image in the appropriate direction
            const slideOutClass = this.slideDirection === 'up' ? 'slide-out-up' : 'slide-out-down';
            const slideInClass = this.slideDirection === 'up' ? 'slide-in-up' : 'slide-in-down';

            this.currentImage.classList.add(slideOutClass);

            setTimeout(() => {
                // Reset all transition classes
                this.currentImage.classList.remove('visible', 'slide-out-up', 'slide-out-down', 'slide-in-up', 'slide-in-down');

                // Load new image
                this.currentImage.src = content.image_url;

                // Start with slide-in position
                this.currentImage.classList.add(slideInClass);
                this.currentImage.style.display = 'block';
                this.noImage.classList.remove('visible');

                // Force reflow to ensure transition works
                this.currentImage.offsetHeight;

                // Slide in to visible position
                this.currentImage.classList.remove(slideInClass);
                this.currentImage.classList.add('visible');

                // Handle image load errors
                this.currentImage.onerror = () => {
                    console.warn('Failed to load image:', content.image_url);
                    this.currentImage.classList.remove('visible');
                    this.currentImage.style.display = 'none';
                    this.noImage.classList.add('visible');
                };
            }, 500); // Wait for slide out
        } else {
            // No image available
            this.currentImage.classList.remove('visible');
            this.currentImage.style.display = 'none';
            this.noImage.classList.add('visible');
        }
    }

    startSlideshow() {
        // Clear any existing timer
        if (this.slideshowTimer) {
            clearInterval(this.slideshowTimer);
        }

        // Auto-advance every 10 seconds (or configured duration)
        this.slideshowTimer = setInterval(() => {
            this.nextSlide();
        }, this.config.slideDuration);
    }

    stopSlideshow() {
        if (this.slideshowTimer) {
            clearInterval(this.slideshowTimer);
            this.slideshowTimer = null;
        }
    }

    nextSlide() {
        if (this.contents.length === 0) return;
        this.slideDirection = 'up'; // Moving to next slides up
        const nextIndex = (this.currentIndex + 1) % this.contents.length;
        this.showSlide(nextIndex);
    }

    previousSlide() {
        if (this.contents.length === 0) return;
        this.slideDirection = 'down'; // Moving to previous slides down
        const prevIndex = (this.currentIndex - 1 + this.contents.length) % this.contents.length;
        this.showSlide(prevIndex);
    }

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            switch (e.key) {
                case 'PageUp':
                    e.preventDefault();
                    this.nextSlide();
                    // Reset slideshow timer
                    this.startSlideshow();
                    break;
                case 'PageDown':
                    e.preventDefault();
                    this.previousSlide();
                    // Reset slideshow timer
                    this.startSlideshow();
                    break;
                case 'Enter':
                    e.preventDefault();
                    this.confirmSelection();
                    break;
                case 'p':
                case 'P':
                    // Pause/resume slideshow
                    e.preventDefault();
                    if (this.slideshowTimer) {
                        this.stopSlideshow();
                        console.log('Slideshow paused');
                    } else {
                        this.startSlideshow();
                        console.log('Slideshow resumed');
                    }
                    break;
            }
        });
    }

    async confirmSelection() {
        if (this.contents.length === 0) return;

        const selectedContent = this.contents[this.currentIndex];
        if (!selectedContent) return;

        console.log('Content selected:', selectedContent);

        // Stop slideshow while playing
        this.stopSlideshow();

        try {
            // Call the play_file API
            const response = await window.fs42Api.post(
                `ppv/${this.config.channelNumber}/play_file`,
                { file_path: selectedContent.video_path }
            );

            console.log('Play command sent:', response);

            // Optionally show a brief confirmation
            // For now, we'll just log it - the video should start playing
            // When the video ends, the player will return to the PPV channel
            // and the slideshow will resume automatically

        } catch (error) {
            console.error('Error sending play command:', error);
            alert(`Failed to play: ${error.detail || error.message}\n\nPress OK to resume slideshow.`);
            // Resume slideshow on error
            this.startSlideshow();
        }
    }

    applyConfiguration() {
        // Apply variation styling
        this.applyVariation();

        // Set background
        if (this.config.backgroundImage) {
            this.backgroundLayer.style.backgroundImage = `url(${this.config.backgroundImage})`;
        } else if (this.config.bgColor) {
            this.container.style.background = this.config.bgColor;
        }

        // Load custom CSS override if provided
        if (this.config.cssOverride) {
            this.loadCSSOverride();
        }
    }

    applyVariation() {
        // Remove any existing variation classes
        this.container.classList.remove('variation-modern', 'variation-retro', 'variation-corporate', 'variation-terminal');

        // Add the selected variation class
        this.container.classList.add(`variation-${this.config.variation}`);
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

        link.onerror = () => {
            console.warn('Failed to load CSS override:', this.config.cssOverride);
        };

        link.onload = () => {
            console.log('CSS override loaded successfully:', this.config.cssOverride);
        };

        document.head.appendChild(link);
    }

    showError(message) {
        this.loadingOverlay.classList.remove('hidden');
        this.loadingOverlay.innerHTML = `
            <div class="loading-text" style="color: #ff4444;">
                Error: ${message}
            </div>
        `;
    }

    async loadMusicPlaylist() {
        try {
            const response = await fetch('music_playlist.json');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            this.musicPlaylist = data.music_files || [];
            console.log('Loaded music playlist:', this.musicPlaylist);
        } catch (error) {
            console.warn('Failed to load music playlist:', error);
            // Continue without music
            this.musicPlaylist = [];
        }
    }

    setupBackgroundMusic() {
        if (!this.bgMusicPlayer || this.musicPlaylist.length === 0) {
            console.log('No background music available');
            return;
        }

        // Set initial volume
        this.bgMusicPlayer.volume = 0.3;

        // Load first track
        this.playMusicTrack(0);

        // When a track ends, play the next one
        this.bgMusicPlayer.addEventListener('ended', () => {
            this.playNextTrack();
        });

        // Handle errors by skipping to next track
        this.bgMusicPlayer.addEventListener('error', (e) => {
            console.warn('Error loading music track:', this.musicPlaylist[this.currentMusicIndex], e);
            this.playNextTrack();
        });
    }

    playMusicTrack(index) {
        if (index < 0 || index >= this.musicPlaylist.length) {
            index = 0;
        }

        this.currentMusicIndex = index;
        this.bgMusicPlayer.src = this.musicPlaylist[index];

        // Try to play the music
        this.bgMusicPlayer.play().then(() => {
            console.log('Playing background music:', this.musicPlaylist[index]);
        }).catch(error => {
            console.warn('Background music autoplay failed:', error);
            // This is expected in some browsers - user interaction may be required
        });
    }

    playNextTrack() {
        // Loop back to first track after last one
        const nextIndex = (this.currentMusicIndex + 1) % this.musicPlaylist.length;
        this.playMusicTrack(nextIndex);
    }

    // Static method to create viewer from URL parameters
    static fromURLParams() {
        const params = new URLSearchParams(window.location.search);

        const channelNumber = params.get('channel');
        if (!channelNumber) {
            console.error('No channel parameter provided');
            return null;
        }

        const config = {
            channelNumber: parseInt(channelNumber),
            variation: params.get('variation') || 'modern',
            cssOverride: params.get('css') || null,
            backgroundImage: params.get('bg') || null,
            bgColor: params.get('bg_color') || null,
            slideDuration: parseInt(params.get('duration')) || 10000
        };

        return new PPVViewer(config);
    }
}

// API for external control
window.PPVViewer = PPVViewer;

// Initialize viewer on page load
document.addEventListener('DOMContentLoaded', () => {
    window.currentPPVViewer = PPVViewer.fromURLParams();

    if (!window.currentPPVViewer) {
        document.getElementById('loadingOverlay').innerHTML = `
            <div class="loading-text" style="color: #ff4444;">
                Error: No channel specified. Please add ?channel=XX to the URL
            </div>
        `;
    }
});
