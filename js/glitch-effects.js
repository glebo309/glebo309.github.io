// Glitch text effect for enhanced aesthetic
function glitchText(element) {
    const originalText = element.textContent;
    const glitchChars = '!<>-_\\/[]{}—=+*^?#________';
    
    setInterval(() => {
        if (Math.random() > 0.95) {
            const glitched = originalText.split('').map(char => {
                if (Math.random() > 0.8) {
                    return glitchChars[Math.floor(Math.random() * glitchChars.length)];
                }
                return char;
            }).join('');
            
            element.textContent = glitched;
            
            setTimeout(() => {
                element.textContent = originalText;
            }, 50);
        }
    }, 100);
}

// Apply glitch effect to section headings
document.addEventListener('DOMContentLoaded', function() {
    const headings = document.querySelectorAll('.section-heading');
    headings.forEach(heading => {
        if (Math.random() > 0.5) {
            glitchText(heading);
        }
    });
});

// Random color shift for backgrounds
function colorShift() {
    const shifts = ['#000000', '#0a0000', '#000a00', '#00000a'];
    let index = 0;
    
    setInterval(() => {
        if (Math.random() > 0.98) {
            document.body.style.backgroundColor = shifts[Math.floor(Math.random() * shifts.length)];
            setTimeout(() => {
                document.body.style.backgroundColor = '#000000';
            }, 100);
        }
    }, 50);
}

if (document.body) {
    colorShift();
}
