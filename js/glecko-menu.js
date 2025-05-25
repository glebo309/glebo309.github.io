window.initGleckoMenu = function () {
	let isMenuOpen = false;
	let isTransitioning = false;
	let storedScrollPosition = 0;

	function closeMenu() {
		if (isTransitioning) return;
		isTransitioning = true;
		isMenuOpen = false;

		// Get current modal scroll position
		const currentModalScroll = $('.perspective--modalview').scrollTop() || 0;
		storedScrollPosition = currentModalScroll;

		console.log('Closing menu, will restore to position:', storedScrollPosition);

		// Clean up scroll event listeners
		$('.perspective, .perspective--modalview').off('scroll.effects');

		$('.outer-nav, .outer-nav li, .outer-nav--return').removeClass('is-vis');
		$('.perspective').removeClass('effect-rotate-left--animate');

		setTimeout(() => {
			// NUCLEAR OPTION: Completely disable 3D transforms during scroll restoration
			const $perspective = $('.perspective');
			const $pageContainer = $('.page-container');

			// Store original styles
			const originalPerspectiveStyle = $perspective.attr('style') || '';
			const originalContainerStyle = $pageContainer.attr('style') || '';

			// Disable ALL transforms and 3D effects temporarily
			$perspective.css({
				'transform': 'none !important',
				'perspective': 'none !important',
				'transform-style': 'flat !important'
			});
			$pageContainer.css({
				'transform': 'none !important',
				'transform-origin': 'initial !important',
				'backface-visibility': 'visible !important'
			});

			// Remove modal classes
			$perspective.removeClass('perspective--modalview effect-rotate-left');

			// Force scroll position immediately
			window.scrollTo(0, storedScrollPosition);
			document.documentElement.scrollTop = storedScrollPosition;
			document.body.scrollTop = storedScrollPosition;

			// Wait a moment, then restore original styles
			setTimeout(() => {
				// Restore original transform styles
				if (originalPerspectiveStyle) {
					$perspective.attr('style', originalPerspectiveStyle);
				} else {
					$perspective.removeAttr('style');
				}
				if (originalContainerStyle) {
					$pageContainer.attr('style', originalContainerStyle);
				} else {
					$pageContainer.removeAttr('style');
				}

				// Final scroll position check
				const finalScroll = window.scrollY || window.pageYOffset || 0;
				console.log(`Final scroll position: ${finalScroll} (target was ${storedScrollPosition})`);

				if (Math.abs(finalScroll - storedScrollPosition) > 10) {
					// Last resort
					window.scrollTo(0, storedScrollPosition);
				}

				isTransitioning = false;
			}, 100);

		}, 400);
	}


	function openMenu() {
		if (isTransitioning) return;
		isTransitioning = true;
		isMenuOpen = true;

		const currentScrollPos = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
		storedScrollPosition = currentScrollPos;

		console.log('Opening menu, current scroll:', storedScrollPosition);

		const $perspective = $('.perspective');
		$perspective[0].scrollTop = 0;
		$perspective.removeClass('perspective--modalview effect-rotate-left effect-rotate-left--animate modalview');
		$perspective.addClass('perspective--modalview effect-rotate-left '); // Add modalview class

		setTimeout(() => {
			$perspective.addClass('effect-rotate-left--animate');
			$('.outer-nav, .outer-nav li, .outer-nav--return').addClass('is-vis');

			setTimeout(() => {
				const $modalView = $('.perspective--modalview');
				$modalView.scrollTop(storedScrollPosition);

				console.log('Modal scroll set to:', $modalView.scrollTop());

				setTimeout(() => {
					setupScrollEffects();
					isTransitioning = false;
				}, 200);
			}, 100);
		}, 50);
	}


	function triggerVideoEffects(scrollContainer) {
		const containerScrollTop = scrollContainer.scrollTop();
		const containerHeight = scrollContainer.height();

		$('video[class*="scroll-fx"], .video-bg-container[class*="scroll-fx"]').each(function () {
			const $video = $(this);
			const $videoContainer = $video.hasClass('video-bg-container') ? $video : $video.closest('.video-bg-container');
			const videoElement = $video.is('video') ? this : $video.find('video')[0];

			if (!videoElement) return;

			const videoTop = $videoContainer.offset().top - scrollContainer.offset().top + containerScrollTop;
			const videoBottom = videoTop + $videoContainer.outerHeight();
			const inViewport = videoBottom > containerScrollTop && videoTop < (containerScrollTop + containerHeight);

			if (inViewport) {
				if (videoElement.hasAttribute('data-src') && !videoElement.src) {
					videoElement.src = videoElement.getAttribute('data-src');
					videoElement.load();
				}

				if ($videoContainer.hasClass('scroll-fx-in-fade')) {
					$videoContainer.addClass('scroll-fx-in-range');
					$videoContainer.css('opacity', '1');
				}

				if (videoElement.hasAttribute('autoplay') && videoElement.paused) {
					videoElement.play().catch(e => console.log('Video autoplay failed:', e));
				}
			} else {
				if ($videoContainer.hasClass('scroll-fx-out-fade')) {
					$videoContainer.css('opacity', '0');
				}
			}
		});
	}

	function triggerScrollEffects(scrollTop) {
		// FIXED: Proper property descriptor management like the old working script
		const originalScrollYDescriptor = Object.getOwnPropertyDescriptor(window, 'scrollY') || 
			Object.getOwnPropertyDescriptor(Window.prototype, 'scrollY') ||
			{ get: function() { return document.documentElement.scrollTop || document.body.scrollTop; }, configurable: true };
			
		const originalPageYOffsetDescriptor = Object.getOwnPropertyDescriptor(window, 'pageYOffset') ||
			Object.getOwnPropertyDescriptor(Window.prototype, 'pageYOffset') ||
			{ get: function() { return document.documentElement.scrollTop || document.body.scrollTop; }, configurable: true };
			
		const originalDocScrollTopDescriptor = Object.getOwnPropertyDescriptor(document.documentElement, 'scrollTop') ||
			Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop') ||
			{ get: function() { return this.scrollTop; }, set: function(val) { this.scrollTop = val; }, configurable: true };

		try {
			Object.defineProperty(window, 'scrollY', { 
				value: scrollTop, 
				configurable: true, 
				writable: false 
			});
			Object.defineProperty(window, 'pageYOffset', { 
				value: scrollTop, 
				configurable: true, 
				writable: false 
			});
			Object.defineProperty(document.documentElement, 'scrollTop', { 
				value: scrollTop, 
				configurable: true, 
				writable: false 
			});

			if (typeof window.scrollFX === 'function') {
				try {
					const scrollEvent = new Event('scroll', { bubbles: true });
					window.scrollFX(scrollEvent);
				} catch (e) {
					console.log('scrollFX error:', e);
				}
			}
			
			if (window.lazySizes && window.lazySizes.checkElems) {
				try {
					window.lazySizes.checkElems();
				} catch (e) {
					console.log('lazySizes error:', e);
				}
			}
			
			if (window.universalParallax && typeof window.universalParallax.refresh === 'function') {
				try {
					window.universalParallax.refresh();
				} catch (e) {
					console.log('universalParallax error:', e);
				}
			}

		} finally {
			// CRITICAL: Restore original property descriptors
			try {
				Object.defineProperty(window, 'scrollY', originalScrollYDescriptor);
			} catch(e) {
				delete window.scrollY;
			}
			
			try {
				Object.defineProperty(window, 'pageYOffset', originalPageYOffsetDescriptor);
			} catch(e) {
				delete window.pageYOffset;
			}
			
			try {
				Object.defineProperty(document.documentElement, 'scrollTop', originalDocScrollTopDescriptor);
			} catch(e) {
				delete document.documentElement.scrollTop;
			}
		}
	}

	function setupScrollEffects() {
		const $scrollContainer = $('.perspective--modalview');

		$scrollContainer.on('scroll.effects', function(e) {
			if (!isMenuOpen) return;

			const scrollTop = $(this).scrollTop();

			clearTimeout(this.scrollTimeout);
			this.scrollTimeout = setTimeout(() => {
				triggerScrollEffects(scrollTop);
				triggerVideoEffects($(this));
			}, 16);
		});

		setTimeout(() => {
			const scrollTop = $scrollContainer.scrollTop();
			triggerScrollEffects(scrollTop);
			triggerVideoEffects($scrollContainer);
		}, 200);
	}

	// Event delegation - will work even with dynamically loaded content
	$(document).on('click', '.header--nav-toggle', function () {
		if ($('.perspective').hasClass('effect-rotate-left--animate')) {
			closeMenu();
		} else {
			openMenu();
		}
	});

	$(document).on('click', '.outer-nav--return', function () {
		closeMenu();
	});

	$(document).on('click', '.outer-nav li', function () {
		closeMenu();
	});

	$(document).on('click', '.effect-rotate-left--animate .page-container', function (e) {
		e.preventDefault();
		e.stopPropagation();
		closeMenu();
	});



};