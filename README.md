
-----

# 🍵 Matcha Kasir Bot - Bot Kasir Telegram

Bot Telegram yang dirancang untuk berfungsi sebagai sistem Point-of-Sale (POS) sederhana, cepat, dan intuitif. Dibuat khusus untuk usaha kecil seperti kedai minuman, booth event, atau warung yang membutuhkan pencatatan transaksi digital tanpa perlu perangkat kasir konvensional.

Bot ini mengimplementasikan alur kerja kasir yang profesional, mulai dari pembukaan sesi, pencatatan pesanan, hingga rekapitulasi penjualan harian.

-----

## ✨ Fitur Utama

  - **🖥️ Antarmuka Intuitif:** Seluruh proses transaksi dilakukan melalui tombol interaktif (*inline keyboard*), meminimalkan kesalahan input dan mempercepat layanan.
  - **🔐 Akses Berbasis Peran (Admin & Kasir):**
      - **Kasir:** Hanya dapat mengakses fungsi transaksi utama.
      - **Admin:** Memiliki akses ke "Admin Panel" untuk melihat rekap penjualan dan mereset data. Tombol admin **sepenuhnya tersembunyi** dari kasir biasa.
  - **🔄 Alur Transaksi Fleksibel:** Setelah transaksi selesai, kasir diberi tiga pilihan strategis:
    1.  **👤 Melayani Pelanggan Baru:** Memulai sesi transaksi baru dari awal.
    2.  **➕ Tambah Item (Pelanggan Sama):** Kembali ke menu untuk menambah pesanan pelanggan yang sama.
    3.  **🚪 Selesai Sesi (Tutup Toko):** Kembali ke halaman sambutan utama untuk mengakhiri sesi kerja.
  - **📊 Panel Admin Fungsional:**
      - Melihat **rekapitulasi penjualan harian** (total omzet, rincian per metode pembayaran).
      - Melihat **total item yang terjual**.
      - **Mereset data transaksi** untuk memulai hari baru.
  - **💳 Mendukung Berbagai Metode Pembayaran:**
      - **Tunai (Cash):** Dengan perhitungan uang kembalian otomatis.
      - **QRIS:** Tampilan konfirmasi untuk pembayaran digital.
  - **🧾 Struk Digital Otomatis:** Setiap transaksi yang berhasil akan menghasilkan struk digital yang rapi dan siap dikirim ke pelanggan.
  - **🧠 Manajemen Sesi Cerdas:** Bot secara otomatis membersihkan data sesi sebelumnya (seperti nama pelanggan dan keranjang) saat memulai transaksi baru untuk mencegah data tumpang tindih.

-----

## 🚀 Instalasi & Konfigurasi

Ikuti langkah-langkah berikut untuk menjalankan bot Anda sendiri.

### 1\. Prasyarat

  - Python 3.8 atau lebih baru.
  - Akun Telegram.

### 2\. Dapatkan Token Bot

1.  Buka Telegram dan cari `@BotFather`.
2.  Kirim perintah `/newbot` dan ikuti instruksinya untuk membuat bot baru.
3.  BotFather akan memberi Anda sebuah **token API**. Simpan token ini baik-baik.

### 3\. Dapatkan User ID Anda

1.  Buka Telegram dan cari `@userinfobot`.
2.  Kirim perintah `/start`, dan bot akan menampilkan User ID Anda.
3.  Catat ID ini. Anda bisa meminta calon pengguna lain (kasir/admin) melakukan hal yang sama untuk mendapatkan ID mereka.

### 4\. Konfigurasi Proyek

1.  **Clone repositori ini:**

    ```bash
    git clone https://github.com/NAMA_USER_ANDA/NAMA_REPO_ANDA.git
    cd NAMA_REPO_ANDA
    ```

2.  **Install dependensi:**

    ```bash
    pip install python-telegram-bot httpx
    ```

3.  **Buka file `.py` utama** dan edit bagian konstanta:

    ```python
    # Ganti dengan token dari BotFather
    TOKEN = "TOKEN_BOT_ANDA" 

    # Masukkan User ID admin (bisa lebih dari satu)
    ADMIN_IDS = [123456789]  

    # Masukkan User ID kasir
    USER_IDS = [987654321, 112233445] 
    ```

    > **Penting:** Seorang admin tidak perlu ditambahkan ke `USER_IDS`. Akses admin sudah mencakup semua hak akses kasir.

### 5\. Jalankan Bot

Setelah konfigurasi selesai, jalankan bot dengan perintah:

```bash
python nama_file_bot_anda.py
```

Bot Anda sekarang sudah aktif di Telegram\!

-----

## 📖 Alur Penggunaan Bot

Berikut adalah alur kerja standar seorang kasir saat menggunakan bot.

1.  **Memulai Bot:** Kasir mengirim perintah `/start` ke bot. Bot akan menampilkan halaman sambutan utama.

2.  **Mulai Sesi Transaksi:** Kasir menekan tombol **"✅ Mulai Sesi Transaksi"**.

3.  **Input Nama Pelanggan:** Bot akan meminta kasir untuk mengetik nama pelanggan.

4.  **Pilih Item Menu:** Tampilan menu utama muncul. Kasir dapat memilih item yang dipesan pelanggan.

5.  **Atur Jumlah Item:** Setelah memilih item, kasir bisa menambah (`➕`) atau mengurangi (`➖`) jumlah pesanan. Keranjang belanja akan ter-update secara otomatis.

6.  **Checkout:** Setelah semua pesanan dimasukkan, kasir menekan tombol **"🛒 Checkout"**. Bot akan menampilkan ringkasan pesanan beserta total tagihan.

7.  **Pilih Metode Pembayaran:** Kasir memilih antara **"💵 Cash"** atau **"📱 QRIS"**.

      - Jika **Cash**, bot akan meminta jumlah uang tunai yang diterima untuk menghitung kembalian.
      - Jika **QRIS**, bot akan menampilkan pesan konfirmasi pembayaran.

8.  **Transaksi Selesai & Struk Dicetak:** Setelah pembayaran dikonfirmasi, bot akan mengirim struk digital.

9.  **Pilih Langkah Selanjutnya:** Bot akan memberikan tiga pilihan: memulai transaksi untuk **pelanggan baru**, **menambah item** untuk pelanggan yang sama, atau **mengakhiri sesi kerja**.

-----

## 🏗️ Struktur Kode

Kode ini dirancang dengan pendekatan fungsional untuk meningkatkan keterbacaan, stabilitas, dan kemudahan pengujian.

  - **`KONSTANTA & KONFIGURASI`**: Tempat untuk semua pengaturan global seperti token, ID pengguna, dan daftar menu.
  - **`STATE MANAGEMENT`**: Menggunakan satu dictionary terpusat `bot_state` untuk mengelola seluruh data sesi pengguna (keranjang, nama pelanggan, view saat ini), mengurangi risiko bug terkait state.
  - **`FUNGSI LOGIKA MURNI`**: Berisi fungsi-fungsi yang tidak memiliki efek samping (misalnya, `calculate_cart_total`, `update_cart`). Fungsi ini hanya menerima input dan menghasilkan output, membuatnya sangat mudah diuji.
  - **`KEYBOARD BUILDERS`**: Kumpulan fungsi yang bertanggung jawab untuk membuat komponen UI (tombol-tombol inline).
  - **`RENDER FUNCTIONS`**: Fungsi yang bertugas mengirim atau mengedit pesan di Telegram, memisahkan aksi (efek samping) dari logika.
  - **`HANDLERS`**: Titik masuk untuk semua interaksi dari pengguna (perintah, teks, klik tombol). Handler berfungsi sebagai "orkestrator" yang memanggil fungsi logika dan render.

-----

## 🤝 Kontribusi

Merasa ada fitur yang bisa ditambahkan atau bug yang perlu diperbaiki? Jangan ragu untuk membuat *Pull Request* atau membuka *Issue*. Kontribusi Anda sangat kami hargai\!

## 📄 Lisensi

Proyek ini dilisensikan di bawah Lisensi MIT. Lihat file `LICENSE` untuk detail lebih lanjut.
