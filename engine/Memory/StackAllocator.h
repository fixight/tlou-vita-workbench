#include <cstdlib>
#include <cstddef>
#include <iostream>


template<typename T>
struct MemorySlice {
    T* data = nullptr;
    size_t count = 0;

    T* begin() const { return data; }
    T* end()   const { return data + count; }

    T& operator[](size_t index) { return data[index]; }
    const T& operator[](size_t index) const { return data[index]; }

    bool isValid() const { return data != nullptr && count > 0; }
};

class StackAllocator {
public:
    using Marker = size_t;

private:
    uint8_t* m_buffer = nullptr;
    size_t m_capacity = 0;
    size_t m_offset = 0;

    static inline size_t alignUp(size_t address, size_t alignment) {
        return (address + (alignment - 1)) & ~(alignment - 1);
    }

public:
    explicit StackAllocator(size_t bytes) {
        m_capacity = bytes;
        m_buffer = static_cast<uint8_t*>(malloc(bytes));
        if (!m_buffer) m_capacity = 0;
    }

    ~StackAllocator() {
        if (m_buffer) free(m_buffer);
    }

    Marker getMarker() const { return m_offset; }

    void freeToMarker(Marker marker) {
        if (marker <= m_offset) {
            m_offset = marker;
        }
    }

    void* allocateBytes(size_t bytes, size_t alignment = 8) {
        size_t currentAddress = reinterpret_cast<size_t>(m_buffer + m_offset);
        size_t alignedAddress = alignUp(currentAddress, alignment);
        size_t alignmentOffset = alignedAddress - reinterpret_cast<size_t>(m_buffer);

        if (alignmentOffset + bytes > m_capacity) {
            std::cerr << "[StackAllocator] ERROR: Out of memory!" << std::endl;
            return nullptr;
        }

        m_offset = alignmentOffset + bytes;
        return reinterpret_cast<void*>(alignedAddress);
    }

    template<typename T>
    MemorySlice<T> allocateSlice(size_t count) {
        if (count == 0) return MemorySlice<T>{ nullptr, 0 };

        T* ptr = static_cast<T*>(allocateBytes(sizeof(T) * count, alignof(T)));
        if (!ptr) return MemorySlice<T>{ nullptr, 0 };

        return MemorySlice<T>{ ptr, count };
    }

    void clear() { m_offset = 0; }
    size_t getUsedMemory() const { return m_offset; }
    size_t getFreeMemory() const { return m_capacity - m_offset; }
};