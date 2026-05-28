// Mermaid 图表点击全屏查看
document.addEventListener('DOMContentLoaded', function() {
    // 创建全屏 overlay
    var overlay = document.createElement('div');
    overlay.className = 'mermaid-overlay';
    overlay.innerHTML = '<button class="mermaid-overlay-close" title="关闭">&times;</button>';
    document.body.appendChild(overlay);

    var closeBtn = overlay.querySelector('.mermaid-overlay-close');

    function closeOverlay() {
        overlay.classList.remove('active');
        overlay.innerHTML = '<button class="mermaid-overlay-close" title="关闭">&times;</button>';
        // 重新绑定关闭按钮
        closeBtn = overlay.querySelector('.mermaid-overlay-close');
        closeBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            closeOverlay();
        });
        document.body.style.overflow = '';
    }

    closeBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        closeOverlay();
    });

    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            closeOverlay();
        }
    });

    // ESC 关闭
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && overlay.classList.contains('active')) {
            closeOverlay();
        }
    });

    // 给所有 mermaid 图绑定点击事件
    function bindMermaidClicks() {
        var diagrams = document.querySelectorAll('.md-typeset .mermaid');
        diagrams.forEach(function(d) {
            if (d.dataset.zoomBound) return;
            d.dataset.zoomBound = 'true';

            d.addEventListener('click', function() {
                var svg = d.querySelector('svg');
                if (!svg) return;
                var clone = svg.cloneNode(true);
                // 保持清晰
                clone.removeAttribute('width');
                clone.removeAttribute('height');
                clone.style.maxWidth = '95vw';
                clone.style.maxHeight = '90vh';

                // 放入 overlay
                overlay.innerHTML = '<button class="mermaid-overlay-close" title="关闭">&times;</button>';
                overlay.appendChild(clone);
                overlay.classList.add('active');

                // 重新绑定关闭按钮
                var newClose = overlay.querySelector('.mermaid-overlay-close');
                newClose.addEventListener('click', function(e) {
                    e.stopPropagation();
                    closeOverlay();
                });

                document.body.style.overflow = 'hidden';
            });
        });
    }

    // 初始绑定
    bindMermaidClicks();

    // MkDocs Material 有 instant navigation，需要监听页面切换
    if (typeof document$ !== 'undefined') {
        document$.subscribe(function() {
            setTimeout(bindMermaidClicks, 100);
        });
    }
});
