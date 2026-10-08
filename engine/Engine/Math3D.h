#ifndef TLOU_MATH3D_HPP
#define TLOU_MATH3D_HPP

#include <cmath>
#include <algorithm>

namespace TLOU {

// Вспомогательные математические константы
constexpr float PI = 3.14159265358979323846f;
constexpr float DEG2RAD = PI / 180.0f;
constexpr float RAD2DEG = 180.0f / PI;

inline float ToRadians(float deg) { return deg * DEG2RAD; }
inline float ToDegrees(float rad) { return rad * RAD2DEG; }

struct Vector2;
struct Vector3;
struct Vector4;

// =========================================================================
// VECTOR 2 (Для UI, 2D координат и текстурных UV сетках)
// =========================================================================
struct Vector2 {
    float x = 0.0f;
    float y = 0.0f;

    constexpr Vector2() = default;
    constexpr Vector2(float x, float y) : x(x), y(y) {}
    explicit constexpr Vector2(float scalar) : x(scalar), y(scalar) {}

    // Математические операторы
    Vector2 operator+(const Vector2& rhs) const { return {x + rhs.x, y + rhs.y}; }
    Vector2 operator-(const Vector2& rhs) const { return {x - rhs.x, y - rhs.y}; }
    Vector2 operator*(float scalar) const { return {x * scalar, y * scalar}; }
    Vector2 operator/(float scalar) const { return {x / scalar, y / scalar}; }

    Vector2& operator+=(const Vector2& rhs) { x += rhs.x; y += rhs.y; return *this; }
    Vector2& operator-=(const Vector2& rhs) { x -= rhs.x; y -= rhs.y; return *this; }
    Vector2& operator*=(float scalar) { x *= scalar; y *= scalar; return *this; }
    Vector2& operator/=(float scalar) { x /= scalar; y /= scalar; return *this; }

    Vector2 operator-() const { return {-x, -y}; }

    // Длина и Нормализация
    float LengthSq() const { return x * x + y * y; }
    float Length() const { return std::sqrt(LengthSq()); }

    Vector2 Normalized() const {
        float len = Length();
        return len > 0.00001f ? *this / len : Vector2(0.0f);
    }
    void Normalize() { *this = Normalized(); }

    float Dot(const Vector2& rhs) const { return x * rhs.x + y * rhs.y; }

    // Базовые направления
    static constexpr Vector2 Zero() { return {0.0f, 0.0f}; }
    static constexpr Vector2 One()  { return {1.0f, 1.0f}; }
};

// =========================================================================
// VECTOR 3 (Главный вектор для 3D: Позиция, Скорость, Поворот, Цвет)
// =========================================================================
struct Vector3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    constexpr Vector3() = default;
    constexpr Vector3(float x, float y, float z) : x(x), y(y), z(z) {}
    explicit constexpr Vector3(float scalar) : x(scalar), y(scalar), z(scalar) {}

    // Математические операторы
    Vector3 operator+(const Vector3& rhs) const { return {x + rhs.x, y + rhs.y, z + rhs.z}; }
    Vector3 operator-(const Vector3& rhs) const { return {x - rhs.x, y - rhs.y, z - rhs.z}; }
    Vector3 operator*(const Vector3& rhs) const { return {x * rhs.x, y * rhs.y, z * rhs.z}; }
    Vector3 operator*(float scalar) const { return {x * scalar, y * scalar, z * scalar}; }
    Vector3 operator/(float scalar) const { return {x / scalar, y / scalar, z / scalar}; }

    Vector3& operator+=(const Vector3& rhs) { x += rhs.x; y += rhs.y; z += rhs.z; return *this; }
    Vector3& operator-=(const Vector3& rhs) { x -= rhs.x; y -= rhs.y; z -= rhs.z; return *this; }
    Vector3& operator*=(float scalar) { x *= scalar; y *= scalar; z *= scalar; return *this; }
    Vector3& operator/=(float scalar) { x /= scalar; y /= scalar; z /= scalar; return *this; }

    Vector3 operator-() const { return {-x, -y, -z}; }

    bool operator==(const Vector3& rhs) const { return x == rhs.x && y == rhs.y && z == rhs.z; }
    bool operator!=(const Vector3& rhs) const { return !(*this == rhs); }

    // Доступ по индексу (v[0], v[1], v[2])
    float& operator[](int index) { return (&x)[index]; }
    const float& operator[](int index) const { return (&x)[index]; }

    // Длина вектора (Magnitude)
    float LengthSq() const { return x * x + y * y + z * z; }
    float Length() const { return std::sqrt(LengthSq()); }

    // Нормализация (Приведение длины к 1.0)
    Vector3 Normalized() const {
        float lenSq = LengthSq();
        if (lenSq < 0.000001f) return Vector3(0.0f);
        float invLen = 1.0f / std::sqrt(lenSq);
        return {x * invLen, y * invLen, z * invLen};
    }
    void Normalize() { *this = Normalized(); }

    // Скалярное произведение (Dot Product)
    float Dot(const Vector3& rhs) const {
        return x * rhs.x + y * rhs.y + z * rhs.z;
    }

    // Векторное произведение (Cross Product) - создает вектор, перпендикулярный обоим
    Vector3 Cross(const Vector3& rhs) const {
        return {
            y * rhs.z - z * rhs.y,
            z * rhs.x - x * rhs.z,
            x * rhs.y - y * rhs.x
        };
    }

    // --- Статические утилиты ---

    // Расстояние между двумя точками
    static float Distance(const Vector3& a, const Vector3& b) {
        return (a - b).Length();
    }

    static float DistanceSq(const Vector3& a, const Vector3& b) {
        return (a - b).LengthSq();
    }

    // Линейная интерполяция (Плавный переход от A к B)
    static Vector3 Lerp(const Vector3& a, const Vector3& b, float t) {
        t = std::clamp(t, 0.0f, 1.0f);
        return a + (b - a) * t;
    }

    // Отражение вектора от нормали (Для физики и отскоков)
    static Vector3 Reflect(const Vector3& v, const Vector3& normal) {
        return v - normal * (2.0f * v.Dot(normal));
    }

    // Быстрые направляющие векторы
    static constexpr Vector3 Zero()    { return { 0.0f,  0.0f,  0.0f}; }
    static constexpr Vector3 One()     { return { 1.0f,  1.0f,  1.0f}; }
    static constexpr Vector3 Up()      { return { 0.0f,  1.0f,  0.0f}; }
    static constexpr Vector3 Down()    { return { 0.0f, -1.0f,  0.0f}; }
    static constexpr Vector3 Left()    { return {-1.0f,  0.0f,  0.0f}; }
    static constexpr Vector3 Right()   { return { 1.0f,  0.0f,  0.0f}; }
    static constexpr Vector3 Forward() { return { 0.0f,  0.0f, -1.0f}; }
    static constexpr Vector3 Back()    { return { 0.0f,  0.0f,  1.0f}; }
};

// Поддержка умножения число * Vector3
inline Vector3 operator*(float scalar, const Vector3& vec) { return vec * scalar; }
inline Vector2 operator*(float scalar, const Vector2& vec) { return vec * scalar; }

// =========================================================================
// VECTOR 4 (Для RGBA Цветов, Плоскостей и Однородных координат)
// =========================================================================
struct Vector4 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float w = 0.0f;

    constexpr Vector4() = default;
    constexpr Vector4(float x, float y, float z, float w) : x(x), y(y), z(z), w(w) {}
    constexpr Vector4(const Vector3& v3, float w) : x(v3.x), y(v3.y), z(v3.z), w(w) {}

    Vector4 operator+(const Vector4& rhs) const { return {x + rhs.x, y + rhs.y, z + rhs.z, w + rhs.w}; }
    Vector4 operator-(const Vector4& rhs) const { return {x - rhs.x, y - rhs.y, z - rhs.z, w - rhs.w}; }
    Vector4 operator*(float scalar) const { return {x * scalar, y * scalar, z * scalar, w * scalar}; }

    static constexpr Vector4 Zero() { return {0.0f, 0.0f, 0.0f, 0.0f}; }
};

} // namespace TLOU

#endif // TLOU_MATH3D_HPP