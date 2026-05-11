package com.emrilab;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;

public class MainActivity extends Activity {

    private WebView webView;
    private ProgressBar progressBar;
    private TextView statusText;

    private static final String STREAMLIT_URL = "http://localhost:8501";
    private static final String FALLBACK_URL   = "https://github.com/Firephase/Start";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Full-screen immersive
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_FULLSCREEN,
            WindowManager.LayoutParams.FLAG_FULLSCREEN
        );

        // Build layout programmatically (no XML inflation needed for API-23 compat)
        RelativeLayout root = new RelativeLayout(this);
        root.setBackgroundColor(0xFF1a1a2e);

        // Status bar at top
        statusText = new TextView(this);
        statusText.setId(View.generateViewId());
        statusText.setText("Connecting to EMRI Lab…");
        statusText.setTextColor(0xFFaaaacc);
        statusText.setTextSize(13f);
        statusText.setPadding(24, 16, 24, 0);
        RelativeLayout.LayoutParams stLp = new RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.MATCH_PARENT, RelativeLayout.LayoutParams.WRAP_CONTENT);
        stLp.addRule(RelativeLayout.ALIGN_PARENT_TOP);
        root.addView(statusText, stLp);

        // Progress bar
        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setId(View.generateViewId());
        progressBar.setMax(100);
        progressBar.setProgress(0);
        RelativeLayout.LayoutParams pbLp = new RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.MATCH_PARENT, 8);
        pbLp.addRule(RelativeLayout.BELOW, statusText.getId());
        root.addView(progressBar, pbLp);

        // WebView
        webView = new WebView(this);
        webView.setId(View.generateViewId());
        RelativeLayout.LayoutParams wvLp = new RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.MATCH_PARENT, RelativeLayout.LayoutParams.MATCH_PARENT);
        wvLp.addRule(RelativeLayout.BELOW, progressBar.getId());
        root.addView(webView, wvLp);

        setContentView(root);

        // WebView settings
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                statusText.setVisibility(View.GONE);
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(WebView view, int errorCode,
                                        String description, String failingUrl) {
                if (failingUrl != null && failingUrl.startsWith("http://localhost")) {
                    // Streamlit not running — show info page
                    webView.loadData(buildOfflinePage(), "text/html", "UTF-8");
                    statusText.setText("Streamlit server not detected");
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url.startsWith("http://localhost") || url.startsWith("http://127.")) {
                    return false; // let WebView handle local URLs
                }
                // External links → system browser
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                if (newProgress == 100) {
                    progressBar.setVisibility(View.GONE);
                }
            }
        });

        webView.loadUrl(STREAMLIT_URL);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    private String buildOfflinePage() {
        return "<!DOCTYPE html><html><head>"
            + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            + "<style>"
            + "body{background:#1a1a2e;color:#ccc;font-family:sans-serif;"
            + "display:flex;flex-direction:column;align-items:center;"
            + "justify-content:center;height:100vh;margin:0;padding:24px;box-sizing:border-box}"
            + "h1{color:#4fc3f7;font-size:1.6em}code{background:#16213e;padding:8px 14px;"
            + "border-radius:6px;display:block;margin:8px 0;font-size:.9em;color:#a5d6a7}"
            + "p{text-align:center;line-height:1.6}"
            + "</style></head><body>"
            + "<h1>EMRI Lab</h1>"
            + "<p>The Streamlit server is not running on this device.<br>"
            + "Start it on a PC/server and connect via local network:</p>"
            + "<code>pip install emri-lab</code>"
            + "<code>streamlit run emri_lab/ui/streamlit_app.py</code>"
            + "<p>Then open in browser or set the server address below.</p>"
            + "<p style='color:#666;font-size:.8em'>EMRI Lab v0.1 · Schwarzschild inspiral simulator</p>"
            + "</body></html>";
    }
}
