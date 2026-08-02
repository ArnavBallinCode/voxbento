export function initLocalModelDownloader() {
  const roomSettingsForm = document.getElementById('floor_translation_form');
  if (roomSettingsForm) {
    roomSettingsForm.addEventListener('submit', async function(e) {
      const transProvider = document.getElementById('floor_translation_provider').value;
      const transModel = document.getElementById('floor_translation_model').value || 'nllb-200-distilled-600M';
      
      if (transProvider === 'local') {
        e.preventDefault();
        try {
          const res = await fetch(`/admin/models/download_progress?model=${encodeURIComponent(transModel)}`);
          if (res.ok) {
            const data = await res.json();
            if (data.status === 'completed') {
              roomSettingsForm.submit();
              return;
            }
          }
        } catch(err) {}
        
        document.getElementById('nllb_download_modal').style.display = 'flex';
      }
    });

    const proceedBtn = document.getElementById('nllb_proceed_btn');
    if (proceedBtn) {
      proceedBtn.addEventListener('click', async function() {
        document.getElementById('nllb_download_modal').style.display = 'none';
        
        const formData = new FormData(roomSettingsForm);
        const actionUrl = roomSettingsForm.getAttribute('action');
        
        try {
          await fetch(actionUrl, {
            method: 'POST',
            body: formData,
            redirect: 'follow'
          });
          
          const transModel = document.getElementById('floor_translation_model').value || 'nllb-200-distilled-600M';
          await fetch('/admin/models/trigger_download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model: transModel})
          });
          
          document.getElementById('nllb_download_progress_container').style.display = 'flex';
          
          const interval = setInterval(async () => {
            const res = await fetch(`/admin/models/download_progress?model=${encodeURIComponent(transModel)}`);
            if (res.ok) {
              const data = await res.json();
              if (data.status === 'downloading' || data.n > 0) {
                const pct = data.total > 0 ? Math.round((data.n / data.total) * 100) : 0;
                const speedMB = data.rate ? (data.rate / (1024 * 1024)).toFixed(1) : '0.0';
                document.getElementById('nllb_download_bar').style.width = pct + '%';
                document.getElementById('nllb_download_percent').textContent = pct + '%';
                document.getElementById('nllb_download_speed').textContent = speedMB + ' MB/s';
              }
              if (data.status === 'completed') {
                clearInterval(interval);
                document.getElementById('nllb_download_progress_container').style.display = 'none';
                document.getElementById('nllb_success_modal').style.display = 'flex';
              } else if (data.status === 'error') {
                clearInterval(interval);
                alert("Failed to download local model.");
                window.location.reload();
              }
            }
          }, 1000);
        } catch (err) {
          console.error("Failed to save or trigger download", err);
          window.location.reload();
        }
      });
    }
    
    const cancelBtn = document.getElementById('nllb_cancel_btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function() {
        document.getElementById('nllb_download_modal').style.display = 'none';
      });
    }

    const gotItBtn = document.getElementById('nllb_success_got_it_btn');
    if (gotItBtn) {
      gotItBtn.addEventListener('click', function() {
        window.location.reload();
      });
    }
  }
}
