// Simple text glitch effect only
document.addEventListener('DOMContentLoaded', function() {
    const headings = document.querySelectorAll('.section-heading');
    
    headings.forEach(heading => {
            const originalText = heading.textContent;
            const glitchChars = '!<>-_\\/[]{}—=+*^?#________';
            
            setInterval(() => {
                if (Math.random() > 0.95) {
                    const glitched = originalText.split('').map(char => {
                        if (Math.random() > 0.8) {
                            return glitchChars[Math.floor(Math.random() * glitchChars.length)];
                        }
                        return char;
                    }).join('');
                    
                    heading.textContent = glitched;
                    
                    setTimeout(() => {
                        heading.textContent = originalText;
                    }, 50);
                }
            }, 100);
    });
});
