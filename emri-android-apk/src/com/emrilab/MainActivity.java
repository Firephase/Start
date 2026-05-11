package com.emrilab;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;

public class MainActivity extends Activity {

    private WebView webView;
    private ProgressBar progressBar;
    private TextView statusText;
    private SharedPreferences prefs;

    private static final String PREF_FILE   = "emrilab_prefs";
    private static final String PREF_SERVER = "server_url";
    private static final String DEFAULT_URL = "http://192.168.1.100:8501";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_FULLSCREEN,
            WindowManager.LayoutParams.FLAG_FULLSCREEN
        );

        prefs = getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE);

        buildLayout();

        String savedUrl = prefs.getString(PREF_SERVER, null);
        if (savedUrl == null) {
            showServerDialog(true);
        } else {
            loadServer(savedUrl);
        }
    }

    private void buildLayout() {
        RelativeLayout root = new RelativeLayout(this);
        root.setBackgroundColor(0xFF1a1a2e);

        // Top bar
        RelativeLayout topBar = new RelativeLayout(this);
        topBar.setId(View.generateViewId());
        topBar.setBackgroundColor(0xFF0f0f1a);
        RelativeLayout.LayoutParams tbLp = new RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.MATCH_PARENT, dp(44));
        tbLp.addRule(RelativeLayout.ALIGN_PARENT_TOP);
        root.addView(topBar, tbLp);

        statusText = new TextView(this);
        statusText.setText("EMRI Lab");
        statusText.setTextColor(0xFF4fc3f7);
        statusText.setTextSize(15f);
        statusText.setPadding(dp(14), 0, 0, 0);
        statusText.setGravity(android.view.Gravity.CENTER_VERTICAL);
        RelativeLayout.LayoutParams stLp = new RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.WRAP_CONTENT, RelativeLayout.LayoutParams.MATCH_PARENT);
        topBar.addView(statusText, stLp);

        // Settings button
        Button settingsBtn = new Button(this);
        settingsBtn.setText("⚙");
        settingsBtn.setTextSize(18f);
        settingsBtn.setBackgroundColor(0x00000000);
        settingsBtn.setTextColor(0xFF4fc3f7);
        settingsBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showServerDialog(false); }
        });
        RelativeLayout.LayoutParams sbLp = new RelativeLayout.LayoutParams(dp(48), dp(44));
        sbLp.addRule(RelativeLayout.ALIGN_PARENT_RIGHT);
        topBar.addView(settingsBtn, sbLp);

        // Progress bar
        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setId(View.generateViewId());
        progressBar.setMax(100);
        RelativeLayout.LayoutParams pbLp = new RelativeLayout.LayoutParams(
            RelativeLayout.LayoutParams.MATCH_PARENT, dp(3));
        pbLp.addRule(RelativeLayout.BELOW, topBar.getId());
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
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setLoadWithOverviewMode(true);
        ws.setUseWideViewPort(true);
        ws.setBuiltInZoomControls(true);
        ws.setDisplayZoomControls(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
                statusText.setText("EMRI Lab");
            }

            @Override
            public void onReceivedError(WebView view, int errorCode,
                                        String description, String failingUrl) {
                if (failingUrl != null && !failingUrl.startsWith("data:")) {
                    String serverUrl = prefs.getString(PREF_SERVER, DEFAULT_URL);
                    webView.loadData(buildOfflinePage(serverUrl), "text/html", "UTF-8");
                    statusText.setText("Нет соединения");
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                String server = prefs.getString(PREF_SERVER, DEFAULT_URL);
                if (url.startsWith(server) || url.startsWith("data:")) return false;
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setVisibility(View.VISIBLE);
                progressBar.setProgress(newProgress);
                if (newProgress == 100) progressBar.setVisibility(View.GONE);
            }
        });
    }

    private void showServerDialog(boolean firstTime) {
        String current = prefs.getString(PREF_SERVER, DEFAULT_URL);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(20), dp(12), dp(20), 0);

        TextView hint = new TextView(this);
        hint.setText("Адрес Streamlit-сервера:\n(запустите на ПК: streamlit run ...)");
        hint.setTextSize(13f);
        hint.setPadding(0, 0, 0, dp(8));
        layout.addView(hint);

        EditText input = new EditText(this);
        input.setText(current);
        input.setSelectAllOnFocus(true);
        layout.addView(input);

        new AlertDialog.Builder(this)
            .setTitle("Подключение к серверу")
            .setView(layout)
            .setPositiveButton("Подключиться", new android.content.DialogInterface.OnClickListener() {
                @Override public void onClick(android.content.DialogInterface d, int w) {
                    String url = input.getText().toString().trim();
                    if (!url.startsWith("http")) url = "http://" + url;
                    prefs.edit().putString(PREF_SERVER, url).apply();
                    loadServer(url);
                }
            })
            .setNegativeButton(firstTime ? "Отмена" : "Закрыть", null)
            .show();
    }

    private void loadServer(String url) {
        statusText.setText("Подключение…");
        webView.loadUrl(url);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    private int dp(int px) {
        return Math.round(px * getResources().getDisplayMetrics().density);
    }

    private String buildOfflinePage(String serverUrl) {
        return "<!DOCTYPE html><html><head>"
            + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            + "<style>body{background:#1a1a2e;color:#ccc;font-family:sans-serif;"
            + "display:flex;flex-direction:column;align-items:center;justify-content:center;"
            + "height:100vh;margin:0;padding:24px;box-sizing:border-box;text-align:center}"
            + "h2{color:#ef9a9a}code{background:#16213e;padding:6px 12px;border-radius:6px;"
            + "display:block;margin:6px 0;color:#a5d6a7;font-size:.9em}"
            + "p{line-height:1.6}</style></head><body>"
            + "<h2>Сервер недоступен</h2>"
            + "<p>Не удалось подключиться к:<br><b>" + serverUrl + "</b></p>"
            + "<p>Запустите Streamlit на ПК в той же сети:</p>"
            + "<code>cd emri-lab</code>"
            + "<code>streamlit run src/emri_lab/ui/streamlit_app.py --server.address 0.0.0.0</code>"
            + "<p>Затем нажмите ⚙ и введите IP вашего ПК.</p>"
            + "</body></html>";
    }
}
