// Diagnostics slideshow functionality for CRT displays
class DiagnosticsSlideshow {
    constructor() {
        this.slides = [];
        this.currentSlide = 0;
        this.slideInterval = null;
        this.slideDuration = 7000; // 7 seconds per slide
        this.diagnosticsData = null;
    }

    async init() {
        await this.loadDiagnosticsData();
        this.createSlides();
        this.startSlideshow();
        this.startTimestampUpdater();
    }

    async loadDiagnosticsData() {
        try {
            this.showLoading();
            this.diagnosticsData = await window.fs42Api.get('player/info');
            this.hideLoading();
        } catch (error) {
            this.showError(`Failed to load diagnostics: ${error.message}`);
            console.error('Failed to load diagnostics:', error);
        }
    }

    createSlides() {
        const container = document.getElementById('slideshow-container');
        container.innerHTML = '';
        this.slides = [];

        if (!this.diagnosticsData) {
            return;
        }

        // Slide 1: System Information
        if (this.diagnosticsData.system) {
            this.slides.push(this.createSlide('SYSTEM INFORMATION', [
                { label: 'Platform', value: this.diagnosticsData.system.platform || 'Unknown' },
                { label: 'Architecture', value: this.diagnosticsData.system.architecture || 'Unknown' },
                { label: 'Hostname', value: this.diagnosticsData.system.hostname || 'Unknown' }
            ]));
        }

        // Slide 2: Temperature
        const tempData = [];
        if (this.diagnosticsData.temperature_c !== undefined) {
            const tempClass = this.getTemperatureClass(this.diagnosticsData.temperature_c);
            tempData.push({ 
                label: 'CPU Temperature', 
                value: `${this.diagnosticsData.temperature_c}°C`,
                class: tempClass
            });
        }
        if (this.diagnosticsData.temperature_f !== undefined) {
            const tempClass = this.getTemperatureClass(this.diagnosticsData.temperature_c);
            tempData.push({ 
                label: 'CPU Temperature', 
                value: `${this.diagnosticsData.temperature_f}°F`,
                class: tempClass
            });
        }
        
        if (tempData.length > 0) {
            this.slides.push(this.createSlide('TEMPERATURE', tempData));
        }

        // Slide 3: Memory Information
        if (this.diagnosticsData.memory) {
            const memData = [];
            if (this.diagnosticsData.memory.total_gb !== undefined) {
                memData.push({ label: 'Total', value: `${this.diagnosticsData.memory.total_gb} GB` });
            }
            if (this.diagnosticsData.memory.used_percent !== undefined) {
                const memClass = this.getMemoryClass(this.diagnosticsData.memory.used_percent);
                memData.push({ 
                    label: 'Used', 
                    value: `${this.diagnosticsData.memory.used_percent}%`,
                    class: memClass
                });
            }
            if (this.diagnosticsData.memory.available_gb !== undefined) {
                memData.push({ label: 'Available', value: `${this.diagnosticsData.memory.available_gb} GB` });
            }
            
            if (memData.length > 0) {
                this.slides.push(this.createSlide('MEMORY STATUS', memData));
            }
        }

        // Slide 4: CPU Information
        if (this.diagnosticsData.cpu) {
            const cpuData = [];
            if (this.diagnosticsData.cpu.cores !== undefined) {
                cpuData.push({ label: 'CPU Cores', value: this.diagnosticsData.cpu.cores.toString() });
            }
            if (this.diagnosticsData.cpu.load_percent !== undefined) {
                cpuData.push({ label: 'CPU Load', value: `${this.diagnosticsData.cpu.load_percent}%` });
            }
            if (this.diagnosticsData.cpu.load_1min !== undefined) {
                cpuData.push({ label: 'Load Avg', value: this.diagnosticsData.cpu.load_1min.toFixed(2) });
            }
            
            if (cpuData.length > 0) {
                this.slides.push(this.createSlide('CPU STATUS', cpuData));
            }
        }

        // Add all slides to container
        this.slides.forEach((slide, index) => {
            slide.style.display = index === 0 ? 'flex' : 'none';
            container.appendChild(slide);
        });
    }

    createSlide(title, dataItems) {
        const slide = document.createElement('div');
        slide.className = 'slide';
        if (this.slides.length === 0) {
            slide.classList.add('active');
        }

        // Header section
        const header = document.createElement('div');
        header.className = 'header';
        
        const slideTitle = document.createElement('div');
        slideTitle.className = 'title';
        slideTitle.textContent = title;
        header.appendChild(slideTitle);

        // Content section
        const content = document.createElement('div');
        content.className = 'content';

        // Limit to 3-4 items per slide for readability
        const itemsToShow = dataItems.slice(0, 4);
        
        itemsToShow.forEach(item => {
            const dataRow = document.createElement('div');
            dataRow.className = 'data-row';

            const label = document.createElement('div');
            label.className = 'label';
            label.textContent = item.label;

            const value = document.createElement('div');
            value.className = 'value';
            value.textContent = item.value;
            
            // Apply color classes for temperature and memory
            if (item.class) {
                value.classList.add(item.class);
            }

            dataRow.appendChild(label);
            dataRow.appendChild(value);
            content.appendChild(dataRow);
        });

        // Footer section
        const footer = document.createElement('div');
        footer.className = 'footer';
        
        const pageInfo = document.createElement('div');
        pageInfo.className = 'page-info';
        pageInfo.textContent = 'FieldStation42';
        
        const timestamp = document.createElement('div');
        timestamp.className = 'timestamp';
        timestamp.textContent = new Date().toLocaleTimeString();
        
        footer.appendChild(pageInfo);
        footer.appendChild(timestamp);

        slide.appendChild(header);
        slide.appendChild(content);
        slide.appendChild(footer);

        return slide;
    }

    getTemperatureClass(tempC) {
        if (tempC > 75) return 'temp-high';
        if (tempC < 40) return 'temp-low';
        return 'temp-normal';
    }

    getMemoryClass(usedPercent) {
        if (usedPercent > 80) return 'memory-high';
        if (usedPercent < 50) return 'memory-low';
        return 'memory-normal';
    }

    startSlideshow() {
        if (this.slides.length <= 1) return;

        this.slideInterval = setInterval(() => {
            this.nextSlide();
        }, this.slideDuration);
    }

    stopSlideshow() {
        if (this.slideInterval) {
            clearInterval(this.slideInterval);
            this.slideInterval = null;
        }
    }

    nextSlide() {
        if (this.slides.length === 0) return;

        // Hide current slide
        this.slides[this.currentSlide].style.display = 'none';
        this.slides[this.currentSlide].classList.remove('active');

        // Move to next slide
        this.currentSlide = (this.currentSlide + 1) % this.slides.length;

        // Show new slide
        this.slides[this.currentSlide].style.display = 'flex';
        this.slides[this.currentSlide].classList.add('active');
    }

    previousSlide() {
        if (this.slides.length === 0) return;

        // Hide current slide
        this.slides[this.currentSlide].style.display = 'none';
        this.slides[this.currentSlide].classList.remove('active');

        // Move to previous slide
        this.currentSlide = this.currentSlide === 0 ? this.slides.length - 1 : this.currentSlide - 1;

        // Show new slide
        this.slides[this.currentSlide].style.display = 'flex';
        this.slides[this.currentSlide].classList.add('active');
    }


    showLoading() {
        const container = document.getElementById('slideshow-container');
        container.innerHTML = `
            <div class="loading">
                <div class="loading-text">LOADING DIAGNOSTICS</div>
                <div class="loading-bar">
                    <div class="loading-fill"></div>
                </div>
            </div>
        `;
    }

    hideLoading() {
        // Loading will be replaced by slides
    }

    showError(message) {
        const container = document.getElementById('slideshow-container');
        container.innerHTML = `
            <div class="error-message">
                <div class="error-title">SYSTEM ERROR</div>
                <div>${message}</div>
            </div>
        `;
    }

    startTimestampUpdater() {
        // Update timestamp every second
        setInterval(() => {
            // Find the timestamp element in the currently active slide
            const activeSlide = document.querySelector('.slide.active');
            if (activeSlide) {
                const timestampElement = activeSlide.querySelector('.timestamp');
                if (timestampElement) {
                    timestampElement.textContent = new Date().toLocaleTimeString();
                }
            }
        }, 1000);
    }

    async refresh() {
        this.stopSlideshow();
        this.currentSlide = 0;
        await this.loadDiagnosticsData();
        this.createSlides();
        this.startSlideshow();
    }
}

// Global slideshow instance
let diagnosticsSlideshow;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', async () => {
    diagnosticsSlideshow = new DiagnosticsSlideshow();
    await diagnosticsSlideshow.init();
});

// Keyboard controls for manual navigation
document.addEventListener('keydown', (event) => {
    if (!diagnosticsSlideshow) return;

    switch(event.key) {
        case 'ArrowRight':
        case ' ':
        case 'n':
            event.preventDefault();
            diagnosticsSlideshow.nextSlide();
            break;
        case 'ArrowLeft':
        case 'p':
            event.preventDefault();
            diagnosticsSlideshow.previousSlide();
            break;
        case 'r':
        case 'F5':
            event.preventDefault();
            diagnosticsSlideshow.refresh();
            break;
        case 'Escape':
            event.preventDefault();
            if (diagnosticsSlideshow.slideInterval) {
                diagnosticsSlideshow.stopSlideshow();
            } else {
                diagnosticsSlideshow.startSlideshow();
            }
            break;
    }
});

// Auto-refresh every 30 seconds
setInterval(() => {
    if (diagnosticsSlideshow) {
        diagnosticsSlideshow.refresh();
    }
}, 30000);